# Installation

`pip install git+https://github.com/YodaPY/vexilux.git`

# Usage

**Example:**
```py
from vexilux import Bot, Command
from lightbulb import member_converter, Context

config = {...}

bot = Bot(**config)

@bot.add_argument("users", ["--users", "-u"], converter=member_converter)
@bot.add_argument("reason", ["--reason", "-r"], greedy=True)
@bot.command(cls=Command)
async def ban(ctx: Context, **options) -> None:
    reason = options.get("reason", "No reason available")
    users = ", ".join(user.username for user in options.get("users"))
    await ctx.respond(
        f"Successfully banned {users} for the reason: {reason}
    )
```

# Documentation

## `vexilux.Bot.add_argument`

The `add_argument` method takes 4 arguments.
- `name`: The name of the argument through which you can access it's value later on
- `aliases`: A list of aliases that should be listened to
- `converter`: A built-in type or a function that takes lightbulb.WrappedArg as argument, defaults to str
- `greedy`: Whether to count all arguments of a flag as one string, defaults to False

If `greedy` is set the flag's value is going to be a string or a converted object!!!
If not, the flag's value of is going to be a list of strings or a list of converted objects.

For commands:
Always make sure to set the `cls` keyword argument inside `lightbulb.command_handler.command` or `lightbulb.commands.command` to `vexilux.commands.Command` in case you want to use CLI-like argument parsing.

For groups:
Always make sure to set the `cls` keyword argument inside `lightbulb.command_handler.group` or `lightbulb.commands.group` to `vexilux.commands.Group` in case you want to use CLI-like argument parsing.

vexilux also supports signatures, you can access them through `vexilux.commands.Command.signature`.