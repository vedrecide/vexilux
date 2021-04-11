import typing
from lightbulb import get_command_signature, Context
from lightbulb import Command as _Command, Group as _Group

class Command(_Command):
    def __init__(self, *args, **kwargs) -> None:
        self.flags = []

        super().__init__(*args, **kwargs)
    
    @property
    def signature(self) -> str:
        if not self.flags:
            return get_command_signature(self)

        signature_elements = [self.qualified_name]

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