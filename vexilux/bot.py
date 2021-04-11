import typing
import hikari
import lightbulb
from .commands import Command, Group

T_converter = typing.Callable[[typing.Union[str, lightbulb.WrappedArg]], typing.Any]

class Bot(lightbulb.Bot):
    """
    A subclass of lightbulb.Bot that allows CLI-like argument parsing
    """

    async def _convert_flag_arg(self, context: lightbulb.Context, arg: str, converter: T_converter) -> typing.Any:
        if isinstance(converter, type):
            converted_arg = converter(arg)

        else:
            converted_arg = await converter(lightbulb.WrappedArg(arg, context))

        return converted_arg

    async def resolve_args_for_command(
        self, context: lightbulb.Context, command: typing.Union[lightbulb.Command, Command], raw_arg_string: str
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

        if isinstance(command, Command) and command.flags:
            flags = {}
            index = 0
            sv = lightbulb.StringView(remainder)
            args, _ = sv.deconstruct_str()

            command_flags = {
                alias: details
                for flag in command.flags
                for alias, details in flag.items()
            }

            while index < len(args):
                element = args[index]
                flag_details = command_flags.get(element)
                index += 1

                if not flag_details:
                    continue

                flag_args = []
                if not index >= len(args):
                    element = args[index]
                    while element not in command_flags:
                        flag_args.append(element)
                        index += 1
                        if index >= len(args):
                            break

                        element = args[index]

                    if flag_details.greedy:
                        flag_args = " ".join(flag_args)

                if isinstance(flag_args, list):
                    converted_flag_args = []

                    for arg in flag_args:
                        converted_arg = await self._convert_flag_arg(context, arg, flag_details.converter)

                        converted_flag_args.append(converted_arg)

                elif isinstance(flag_args, str):
                    converted_flag_args = await self._convert_flag_arg(context, flag_args, flag_details.converter)

                flags[flag_details.name] = converted_flag_args

            remainder = flags

        return positional_args, remainder

    async def _invoke_command(
        self,
        command: lightbulb.Command,
        context: lightbulb.Context,
        args: typing.Sequence[str],
        kwarg: typing.Mapping[str, str],
    ) -> None:
        if kwarg:
            await command.invoke(context, *args, **kwarg)
        elif args:
            await command.invoke(context, *args)
        else:
            await command.invoke(context)

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
            await self._invoke_command(command, context, positional_args, keyword_arg)
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