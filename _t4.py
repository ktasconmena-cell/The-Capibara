import os, asyncio, traceback, discord, bot as b

async def main():
    cli = discord.Client(intents=discord.Intents.default())

    @cli.event
    async def on_ready():
        g = cli.get_guild(b.GUILD_ID)
        canal = g.get_channel(1558483859996278914)
        print("--- purgar_mensajes ---")
        try:
            n = await b.purgar_mensajes(canal, b.DELETE_AFTER_MINUTES)
            print("  OK    borrados:", n)
        except Exception:
            traceback.print_exc()

        # motivo_aislar con miembros traidos por REST (sin intent privilegiado)
        print("\n--- motivo_aislar sobre 6 miembros reales (NO aisla a nadie) ---")
        import requests
        h = {"Authorization": f"Bot {os.environ['DISCORD_BOT_TOKEN']}"}
        datos = requests.get(
            f"https://discord.com/api/v10/guilds/{b.GUILD_ID}/members?limit=300",
            headers=h).json()
        for d in [x for x in datos if not x["user"]["bot"]][:6]:
            rol = discord.Object(id=0)
            miemb = discord.Member(state=cli._connection, data=d, guild=g)
            try:
                r = b.motivo_aislar(miemb)
                print(f"  OK    {d['user']['username']:<18} -> {r or 'SE PUEDE AISLAR'}")
            except Exception as e:
                print(f"  FALLO {d['user']['username']}: {type(e).__name__}: {e}")
        await cli.close()

    await cli.start(os.environ["DISCORD_BOT_TOKEN"])

asyncio.run(main())
