# Chicken Archer / FLAME Support Bot

Telegram support bot for anonymous suggestions, bug reports, and other feedback.

## Railway variables

Create these two variables in Railway:

- `BOT_TOKEN` – token from @BotFather. Never commit it to GitHub.
- `ADMIN_CHAT_ID` – your private Telegram chat ID.

## Deploy

1. Set Railway Root Directory to `/support-bot`.
2. Add `BOT_TOKEN` and `ADMIN_CHAT_ID` in Railway Variables.
3. Deploy the service. It runs using Telegram long polling.
4. Open your bot in Telegram and send `/start`.
5. Send `/myid` in your private chat to obtain the admin chat ID before setting the variable.

## Privacy

The bot does not forward the sender's name, username, or Telegram ID to the developer, and it does not write sender identifiers to a database. Telegram as a platform technically processes messages, so this is not absolute anonymity from Telegram. Do not ask users to submit personal information.
