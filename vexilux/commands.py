import attr
import typing
import inspect
from lightbulb import get_command_signature, Context, WrappedArg
from lightbulb import Command as _Command, Group as _Group

T_converter = typing.Callable[[typing.Union[str, WrappedArg]], typing.Any]

@attr.s
class FlagDetails:
    """
    Dataclass holding information for a flag
    """

    name: str = attr.ib()
    converter: T_converter = attr.ib()
    greedy: bool = attr.ib()

class Command(_Command):
    def __init__(self, *args, **kwargs) -> None:
        self.flags = []

        super().__init__(*args, **kwargs)
    
    @property
    def signature(self) -> str:
        signature_elements = [self.qualified_name]

        for argname, arginfo in self.arg_details.args.items():
            if arginfo.ignore:
                continue

            if arginfo.argtype in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_KEYWORD) and self.flags:
                break

            if arginfo.default is inspect.Parameter.empty:
                signature_elements.append(f"<{argname}>")

            else:
                signature_elements.append(f"[{argname}={arginfo.default}]")

        for flag in self.flags:
            aliases = " | ".join(
                sorted(
                    flag, key=lambda alias: len(alias)
                )
            )
            flag_signature = f"{aliases} [...]"
            signature_elements.append(flag_signature)

        return " ".join(signature_elements)

    async def invoke(self, context: Context, *args: str, **kwargs: str) -> typing.Any:
        """
        Invoke the command with given args and kwargs. Cooldowns and converters will
        be processed however this method bypasses all command checks.
        Args:
            context (:obj:`~.context.Context`): The command invocation context.
            *args: The positional arguments to invoke the command with.
        Keyword Args:
            **kwargs: The keyword arguments to invoke the command with.
        """

        if self.cooldown_manager is not None:
            self.cooldown_manager.add_cooldown(context)
        # Add the start slice on to the length to offset the section of arg_details being extracted
        arg_details = list(self.arg_details.args.values())[1 : len(args) + 1]
        new_args = await self._convert_args(context, args[: len(arg_details)], arg_details)
        new_args = [*new_args, *args[len(arg_details) :]]

        return await self._callback(context, *new_args, **kwargs)

class Group(_Group, Command):
    pass

def add_argument(
    name: str,
    aliases: typing.List[str],
    /,
    *,
    converter: T_converter=str,
    greedy: bool=False
):
    """
    Decorator to add a flag argument to a command

    Args:
        - name: The name of the argument through which you can access it's value later on
        - aliases: A list of aliases that should be listened to
        - converter: A built-in type or a function that takes lightbulb.WrappedArg as argument, defaults to str
        - greedy: Whether to count all arguments of a flag as one string, defaults to False
    """
    def decorate(command: typing.Union[Command, Group]):
        command.flags.append(
            {
                alias: FlagDetails(name, converter, greedy)
                for alias in aliases
            }
        )

        return command

    return decorate