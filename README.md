# Usage

**Example:**
```py
from vexilux import Bot
from lightbulb import member_converter, Context

config = {...}

bot = Bot(**config)

@bot.add_argument("users", ["--users", "-u"], converter=member_converter)
@bot.add_argument("reason", ["--reason", "-r"], greedy=True)
async def ban(ctx: Context, **options) -> None:
    reason = options.get("reason", ["No reason available"])
    users = ", ".join(user.username for user in options.get("users"))
    await ctx.respond(
        f"Successfully banned {users} for the reason: {reason[0]}
    )
```