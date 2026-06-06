import os, json, datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import anthropic

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
MY_ID = int(os.getenv("MY_TELEGRAM_ID", "0"))

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

TJ_MEMORY = """
IDENTITY: TJ Stanek, Account Manager at TEKsystems Kansas City, focused on Data/AI/Analytics/Enterprise Applications.
ACCOUNTS: Terracon, Burns & McDonnell, Black & Veatch, HNTB, Hill's Pet Nutrition, SS&C/DST, Dairy Farmers of America, JE Dunn, Creative Planning, BlueScope.
FINANCE: VTI-heavy DCA investor, Roth IRA + Roth 401k + taxable brokerage + HYSA. Owns 2 Omaha rental properties with siblings. FIRE goal with Lake Como retirement target.
PERSONAL: Based in Overland Park KS. KC Royals fan. Avid golfer, owns Bushnell Wingman. Girlfriend: Katie. Sigma Chi alum, UNL grad May 2025 (BS Business Admin, Marketing).
WORK STYLE: Direct, concise, no filler. Prefers action over explanation.
"""

WORKOUT_PLAN = {
    "Monday":    "PUSH - Bench Press 4x5, OHP 3x8, Incline DB Press 3x10, Lateral Raises 3x15, Tricep Pushdowns 3x12",
    "Tuesday":   "PULL - Deadlift 4x5, Bent-Over Row 3x8, Pull-Ups 3x8, Face Pulls 3x15, Hammer Curls 3x12",
    "Wednesday": "LEGS - Squat 4x5, Romanian Deadlift 3x8, Leg Press 3x12, Walking Lunges 3x10, Calf Raises 4x15",
    "Thursday":  "PUSH - OHP 4x5, DB Bench 3x10, Cable Flyes 3x12, Lateral Raises 3x15, Skull Crushers 3x10",
    "Friday":    "PULL - Pull-Ups 4x8, Barbell Row 4x8, Seated Cable Row 3x12, Rear Delt Flyes 3x15, Barbell Curls 3x10",
    "Saturday":  "ACTIVE RECOVERY - 18 holes golf or 45 min zone 2 cardio + mobility work",
    "Sunday":    "REST - Optional light walk or stretching only",
}

GROCERY_FILE = "groceries.json"

def load_groceries():
    if os.path.exists(GROCERY_FILE):
        with open(GROCERY_FILE) as f:
            return json.load(f)
    return {"items": [], "last_bought": None, "frequency_days": 7}

def save_groceries(data):
    with open(GROCERY_FILE, "w") as f:
        json.dump(data, f, indent=2)

def grocery_status():
    data = load_groceries()
    items = data.get("items", [])
    last = data.get("last_bought")
    freq = data.get("frequency_days", 7)
    reminder = ""
    if last:
        last_date = datetime.datetime.fromisoformat(last)
        days_since = (datetime.datetime.now() - last_date).days
        days_left = freq - days_since
        if days_left <= 2:
            reminder = f"GROCERY RUN DUE - only {days_left} day(s) left (last bought {days_since} days ago)"
        else:
            reminder = f"Next grocery run in ~{days_left} days"
    return items, reminder

def build_system_prompt():
    today = datetime.datetime.now().strftime("%A, %B %d %Y")
    day = datetime.datetime.now().strftime("%A")
    workout = WORKOUT_PLAN.get(day, "Rest day")
    items, reminder = grocery_status()
    return f"""You are TJ's personal assistant. Be extremely concise and direct. No filler words. No unnecessary explanation.

ABOUT TJ:
{TJ_MEMORY}

TODAY: {today}

TODAY'S WORKOUT ({day}): {workout}

GROCERY LIST: {', '.join(items) if items else 'Empty'}

{reminder}

AVAILABLE COMMANDS:
/workout - give today's full workout with sets, reps, and 1-line tip
/groceries - show list and days until next run
/add [item] - add item to grocery list
/bought - mark groceries purchased, reset timer
/markets - search web, return top 4 market-moving events today with specific numbers
/ai - search web, return top 5 AI and tech developments, always include Claude/Anthropic news if any exists
/brief - full morning briefing: workout + top 3 market events + top 3 AI news

RULES:
- Only respond to user ID: {MY_ID}
- Keep all responses under 280 words unless user asks for detail
- For /markets and /ai always use web search - never answer from memory
- Always include specific numbers, names, percentages when reporting market or AI news
- Grocery reminder: if days_left <= 2 always surface the warning at top of any response"""

conversation_history = {}

def get_history(uid):
    return conversation_history.get(uid, [])

def add_to_history(uid, role, content):
    if uid not in conversation_history:
        conversation_history[uid] = []
    conversation_history[uid].append({"role": role, "content": content})
    if len(conversation_history[uid]) > 10:
        conversation_history[uid] = conversation_history[uid][-10:]

async def ask_claude(uid, message):
    add_to_history(uid, "user", message)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=600,
        system=build_system_prompt(),
        messages=get_history(uid),
        tools=[{"type": "web_search_20250305", "name": "web_search"}]
    )
    reply = ""
    for block in response.content:
        if hasattr(block, "text"):
            reply += block.text
    if not reply:
        reply = "Done."
    add_to_history(uid, "assistant", reply)
    return reply

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        return
    text = update.message.text
    uid = update.effective_user.id
    if text.lower().startswith("/add "):
        item = text[5:].strip()
        data = load_groceries()
        if item and item not in data["items"]:
            data["items"].append(item)
            save_groceries(data)
        await update.message.reply_text(f"Added: {item}\nList: {', '.join(data['items'])}")
        return
    if text.lower() == "/bought":
        data = load_groceries()
        data["last_bought"] = datetime.datetime.now().isoformat()
        data["items"] = []
        save_groceries(data)
        await update.message.reply_text("Marked purchased. Timer reset. List cleared.")
        return
    await update.message.reply_text("Processing...")
    reply = await ask_claude(uid, text)
    await update.message.reply_text(reply)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hey TJ! Online and ready.\n\nCommands:\n/workout\n/groceries\n/add [item]\n/bought\n/markets\n/ai\n/brief")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    print("Bot running...")
    app.run_polling()
