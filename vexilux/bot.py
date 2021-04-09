import attr
import typing
import hikari
import lightbulb

@attr.s
class FlagDetails:
    """
    Dataclass holding information for a flag
    """

    name: str = attr.ib()
    converter: typing.Callable[[typing.Union[str, lightbulb.WrappedArg]], typing.Any] = attr.ib()
    greedy: bool = attr.ib()

class Bot(lightbulb.Bot):
    """
    A subclass of lightbulb.Bot that allows CLI-like argument parsing
    """

    async def resolve_args_for_command(
        self, context: lightbulb.Context, command: lightbulb.Command, raw_arg_string: str
    ) -> typing.Tuple[typing.List[str], typing.Dict[str, str]]:
        sv = lightbulb.StringView(raw_arg_string)
        positional_args, remainder = sv.deconstruct_str(max_parse=command.arg_details.maximum_arguments)
        if remainder and command.arg_details.kwarg_name is None and not command._allow_extra_arguments:
            raise lightbulb.errors.TooManyArguments(command)
        if (len(positional_args) + bool(remainder)) < command.arg_details.minimum_arguments:
            missing_args = command.arg_details.get_missing_args([*positional_args, *([remainder] if remainder else [])])
            raise lightbulb.errors.NotEnoughArguments(command, missing_args)

        remainder = remainder or {}

        if remainder and command.arg_details.kwarg_name is not None:
            remainder = {command.arg_details.kwarg_name: remainder}

        flags = {}
        index = 0
        sv = lightbulb.StringView(remainder)
        args, _ = sv.deconstruct_str()
        while index < len(args):
            element = args[index]
            flag_details = command.flags.get(element)
            if not flag_details:
                index += 1
                continue

            index += 1

            flag_args = []
            if not index >= len(args):
                element = args[index]
                while element not in command.flags:
                    flag_args.append(element)
                    index += 1
                    if index >= len(args):
                        break

                    element = args[index]

                if flag_details.greedy:
                    flag_args = [" ".join(flag_args)]

            converted_flag_args = []

            for arg in flag_args:
                if isinstance(flag_details.converter, type):
                    converted_arg = flag_details.converter(arg)

                else:
                    converted_arg = await flag_details.converter(lightbulb.WrappedArg(arg, context))

                converted_flag_args.append(converted_arg)

            flags[flag_details.name] = converted_flag_args

        return positional_args, flags

    async def invoke_command(
        self,
        command: lightbulb.Command,
        context: lightbulb.Context, 
        *args: str, **kwargs: str
    ) -> typing.Any:
        if command.cooldown_manager is not None:
            command.cooldown_manager.add_cooldown(context)

        arg_details = list(command.arg_details.args.values())[1 : len(args) + 1]
        new_args = await command._convert_args(context, args[: len(arg_details)], arg_details)
        new_args = [*new_args, *args[len(arg_details) :]]

        return await command._callback(context, *new_args, **kwargs)

    async def _pass_args_to_invocation(
        self,
        command: lightbulb.Command,
        context: lightbulb.Context,
        args: typing.Sequence[str],
        kwarg: typing.Mapping[str, str],
    ) -> None:
        if kwarg:
            await self.invoke_command(command,context, *args, **kwarg)
        elif args:
            await self.invoke_command(command, context, *args)
        else:
            await self.invoke_command(command, context)

    async def process_commands_for_event(self, event: hikari.MessageCreateEvent) -> None:
        """
        Carries out all command and argument parsing, evaluates checks and ultimately invokes
        a command if the event passed is deemed to contain a command invocation.
        It is not recommended that you override this method - if you do you should make sure that
        you know what you are doing.
        Args:
            event (:obj:`hikari.MessageCreateEvent`): The event to process commands for.
        Returns:
            ``None``
        """
        prefix = await self._resolve_prefix(event.message)
        if prefix is None:
            return

        new_content = event.message.content[len(prefix) :]

        if not new_content or new_content.isspace():
            return

        split_args = lightbulb.command_handler.ARG_SEP_REGEX.split(new_content, maxsplit=1)
        invoked_with, command_args = split_args[0], "".join(split_args[1:])

        try:
            command = self._validate_command_exists(invoked_with)
        except lightbulb.errors.CommandNotFound as ex:
            await self._dispatch_command_error_event_from_exception(ex, event.message)
            return

        temp_args = command_args
        final_args = command_args
        while isinstance(command, lightbulb.Group) and command_args:
            next_split = lightbulb.command_handler.ARG_SEP_REGEX.split(temp_args, maxsplit=1)
            next_arg, temp_args = next_split[0], "".join(next_split[1:])
            prev_command = command
            maybe_subcommand = command.get_subcommand(next_arg)

            if maybe_subcommand is None:
                command = prev_command
                break
            else:
                command = maybe_subcommand
                final_args = temp_args

        context = self.get_context(event.message, prefix, invoked_with, command)

        await self.dispatch(lightbulb.CommandInvocationEvent(app=self, command=command, context=context))
        if (before_invoke := command._before_invoke) is not None:
            await before_invoke(context)

        try:
            positional_args, keyword_arg = await self.resolve_args_for_command(context, command, final_args)
            await self._evaluate_checks(command, context)
        except (
            lightbulb.errors.NotEnoughArguments,
            lightbulb.errors.TooManyArguments,
            lightbulb.errors.CheckFailure,
            lightbulb.errors.CommandSyntaxError,
        ) as ex:
            await self._dispatch_command_error_event_from_exception(ex, event.message, context, command)
            return

        try:
            await self._pass_args_to_invocation(command, context, positional_args, keyword_arg)
        except lightbulb.errors.CommandError as ex:
            await self._dispatch_command_error_event_from_exception(ex, event.message, context, command)
            return
        except Exception as ex:
            new_ex = lightbulb.errors.CommandInvocationError(f"{type(ex).__name__}: {ex}", ex)
            await self._dispatch_command_error_event_from_exception(new_ex, event.message, context, command)
            return

        if (after_invoke := command._after_invoke) is not None:
            await after_invoke(context)

        await self.dispatch(lightbulb.CommandCompletionEvent(app=self, command=command, context=context))

    def add_argument(
        self,
        name: str,
        aliases: typing.List[str],
        /,
        *,
        converter: typing.Callable[[typing.Union[str, lightbulb.WrappedArg]], typing.Any]=str,
        greedy: bool=False
    ):
        """
        Decorator to add a flag argument to a command

        Args:
            - name: The name of the argument through which you can access it's value later on
            - aliases: A list of aliases that should be listened to
            - converter: A built-in type or a function that takes lightbulb.WrappedArg as argument, defaults to str
            - greedy: Whether to count all arguments of a flag as one string
        """
        def decorate(command: lightbulb.Command):
            if not hasattr(command, "flags"):
                setattr(command, "flags", {})

            for alias in aliases:
                command.flags[alias] = FlagDetails(name, converter, greedy)

            return command

        return decorate