from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request, render_template, redirect
from dotenv import load_dotenv
from datetime import datetime, time 
import os
from apscheduler.schedulers.background import BackgroundScheduler
from helper_functions import LunchBot,decode_token
from db_config import db,users_collection,poll_collection


load_dotenv()

token = os.environ.get("SLACK_ENTRI_LUNCH_BOT_TOKEN")
signing_secret = os.environ.get("SLACK_SIGNING_SECRET")
enrti_lunch_channel_id = os.environ.get("ENTRI_LUNCH_CHANNEL_ID")
ADMINS = eval(os.environ.get("ADMINS"))
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
QR_CODE_LINK = os.environ.get("QR_CODE_LINK")


app = App(
    token=token,
    signing_secret=signing_secret
)


daily_poll_start_time = time(1, 57)
daily_poll_end_time = time(1, 58)
current_datetime = datetime.now().replace(microsecond=0)
poll_start_datetime = datetime.combine(current_datetime, daily_poll_start_time)
poll_end_datetime = datetime.combine(current_datetime, daily_poll_end_time)



lunch_bot = LunchBot(
                app=app,
                users_collection=users_collection,
                poll_collection=poll_collection
)

lunch_poll=lunch_bot.create_lunch_poll(
                    poll_start_datetime=poll_start_datetime,
                    poll_end_datetime=poll_end_datetime,
)

# Initializes your app with your bot token and signing secret


flask_app = Flask(__name__)
handler = SlackRequestHandler(app)
scheduler = BackgroundScheduler()


#functions


#action and events

@app.action("poll_vote")
def handle_poll_vote(ack,body,say):
    ack()
    if lunch_poll.is_poll_expired():
        say("Sorry, poll expired!!")
    else:
        slack_id = body.get('user').get("id")
        value = body.get("actions")[0].get("selected_option").get("value")
        ts = body.get("container").get("message_ts")
        
        if value=="True":
            print("ts--",lunch_poll.ts)         #note: value of value is a string not Bool.
            result = lunch_poll.poll_yes(
                slack_id=slack_id,
                ts=ts
            )
        else:
            result = lunch_poll.poll_no(
                slack_id=slack_id,
                ts=ts
            )





@app.message("##poll_count")
def message_hello(message, say):
    print("inside message")
    user = message.get("user")
    print(f"user - {user}")
    print(f"admins {ADMINS}")
    if user in ADMINS:
        count = lunch_poll.get_poll_count()
        say(f"count: {count}")
    else:
        say(f"ayn nee ethaada ...!")
    # say() sends a message to the channel where the event was triggered
    


#routes
@flask_app.route("/slack/poll", methods=["POST"])
def slack_poll():
    return handler.handle(request)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    print("event recorded")
    if request.headers["Content-Type"] == "application/json":
        data = request.json
        if "challenge" in data:
            return data.get("challenge"),200
        return handler.handle(request)
    else:
        return "",200



@flask_app.route("/poll/verify/<poll_token>", methods=["GET","POST"])
def verify_poll_token(poll_token):
    payload = decode_token(poll_token)
    print("Payload",payload)
    if True:
        if request.method=="GET":
            return render_template("submit_secret_key.html",poll_token=poll_token)

        if request.method=="POST":
            secret_key = request.form.get("secret_key")
            print("secret_key",secret_key)
            print("jwt_secret_key",JWT_SECRET_KEY)
            
            if secret_key!=JWT_SECRET_KEY:
                print("failed")
                return render_template("not_verified.html")
                        
            print("verithanam")
            verified = lunch_poll.verify_poll(payload)
            print("verified",verified)        
            return render_template("verified.html") if verified else render_template("not_verified.html") 


#@flask_app.route
    #1st renders template with an input to receive secret_key - admin has to to type
        #in that template - poll_token must br recorded and along with secret_key it must be sent to this url.
    #if verified - render template - verified.html
        #if not - render template - not_verfied.html



scheduler.add_job(
    lambda:lunch_poll.post_and_db_insert(enrti_lunch_channel_id),
    'cron',
    hour=daily_poll_start_time.hour,
    minute=daily_poll_start_time.minute
)

            
scheduler.add_job(
    lambda:lunch_bot.post_poll_expired(enrti_lunch_channel_id),
    'cron',
    hour=daily_poll_end_time.hour,
    minute=daily_poll_end_time.minute
)


scheduler.add_job(
    lambda:lunch_bot.send_qr_code_to_users(lunch_poll.ts),
    'cron' ,
    hour=daily_poll_end_time.hour,
    minute = daily_poll_end_time.minute + 1
)



if __name__=="__main__":
    print("main is on!")
    print(db)
    scheduler.start()
    flask_app.run(port=3000, debug=True, use_reloader=False)


# pip install -r requirements.txt
# export SLACK_SIGNING_SECRET=***
# export SLACK_BOT_TOKEN=xoxb-***
# FLASK_APP=app.py FLASK_ENV=development flask run -p 3000

