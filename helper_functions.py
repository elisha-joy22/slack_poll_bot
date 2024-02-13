from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from datetime import datetime, timedelta
from abc import ABC
import qrcode
import jwt
import os
import base64
#logging.basicConfig(level=logging.DEBUG)
from db_ops import PollDB
import shutil

load_dotenv()

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
QR_CODE_LINK = os.environ.get("QR_CODE_LINK")

class ContentPoster():
    def __init__(self,app):
        self.app = app 

    def post_content(self,channel_id,text,blocks=None):
        try:
            response = self.app.client.chat_postMessage(
                channel=channel_id,
                text=text,
                blocks=blocks
            )
            return response
        except SlackApiError as e:
            print(f"Error posting content: {e.response['error']}")


    def update_posted_content(self,channel_id,text,ts,blocks=None):
        print(f"channel in update_content\n{channel_id}\ntext{text}\nts{ts}")
        try:
            response = self.app.client.chat_update(
                channel=channel_id,
                ts=ts,
                text=text
                #blocks=blocks
            )
            return response
        except SlackApiError as e:
            print(f"Error posting content: {e.response['error']}")


    def post_file(self,channel_id,title):
        print("channel_id",channel_id)
        self.app.client.files_upload(
            file=f"{channel_id}.png",
            channels=channel_id,
            title=title
        )


class LunchBot(ContentPoster):
    def __init__(self,app,users_collection,poll_collection):
        self.app=app
        self.poll = None
        self.users_collection = users_collection
        self.poll_collection = poll_collection
        super().__init__(app)

    def create_lunch_poll(self,poll_start_datetime,poll_end_datetime):
        current_datetime = datetime.now().replace(microsecond=0)
        lunch_datetime = current_datetime.replace(hour=12,minute=30,second=0)+timedelta(days=1)
        question = f"Will you join us for lunch tomorrow {lunch_datetime}?"
        poll = Poll(
            app=self.app,
            question=question,
            poll_start_datetime=poll_start_datetime,
            poll_end_datetime=poll_end_datetime,
            event_datetime=lunch_datetime, 
            collection=self.poll_collection,
        )
        print("poll created!!")
        self.poll = poll
        return self.poll


    def post_poll_expired(self,channel_id):
        print("tssss",self.poll.ts)
        poll_count=self.poll.get_poll_count(self.poll.ts)
        result = self.poll.db_update({'ts':self.poll.ts},{'poll_closed':True})
        text1=f"No more responses, Poll expired for lunch {self.poll.event_datetime}. Thank you!!"
        text2 = f"\nTodays poll count - {poll_count}"
        text3 = f"\nThank you !!"
        text = text1 + text2 + text3
        print("expiry-result",result)
        self.update_posted_content(channel_id,text=text,ts=self.poll.ts)
        print("post expired...")


    def send_qr_code_to_users(self,ts):
        users = self.poll.get_polled_users(ts)
        directory = "qr_code_images"
        os.makedirs(directory, exist_ok=True)
        for user in users:
            user_id = user.get("user_id")
            secret_data = user.get("secret_data")
            token = generate_token(user_id,ts,secret_data)
            link = QR_CODE_LINK + token
            generate_qr_code(link,user_id)
            title="Hey, This is your QR code for verification for the lunch tomorrow\nEnjoy lunch!!"
            self.post_file(user_id,title)
        try:
            #shutil.rmtree(directory)
            print(f"Directory {directory} and its contents removed successfully.")
        except Exception as e:
            print(f"An error occurred while removing directory: {e}")



class PollBlockBuilder():
    def __init__(self):
        pass
    
    def create_yes_no_poll_block(self, question, poll_expiry_datetime):
        poll_end_time = poll_expiry_datetime.strftime("%H:%M")
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{question}\n*(Please vote by selecting an option)*\nThis poll will expire at {poll_end_time}."
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "radio_buttons",
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Yes"
                                },
                                "value": "True"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "No"
                                },
                                "value": "False"
                            }
                        ],
                        "action_id": "poll_vote"
                    }
                ]
            }
        ]

        return blocks



class PollInterface(ABC):
    def is_poll_expired():
        pass

    def post():
        pass 




class Poll(PollInterface,PollDB):
    def __init__(self,app,question,poll_start_datetime,poll_end_datetime,event_datetime,collection):
        self.poll_start_datetime = poll_start_datetime
        self.poll_end_datetime = poll_end_datetime
        self.question = question
        self._poll_block = PollBlockBuilder().create_yes_no_poll_block(self.question,self.poll_end_datetime)
        self.collection = collection
        self._content_poster = ContentPoster(app)
        self.event_datetime = event_datetime
        self.ts = None

    def get_poll_block(self):
        return self._poll_block

    def set_poll_block(self,poll_block):
        self._poll_block = poll_block

    def is_poll_expired(self):
        current_datetime = datetime.now().replace(microsecond=0)
        print(f"expiration date time - {self.poll_end_datetime}")
        return current_datetime >= self.poll_end_datetime

    def post(self,channel_id):
        try:
            post_content = self._content_poster.post_content(
                channel_id=channel_id,
                text=self.question,
                blocks=self._poll_block)
            return post_content
        except Exception as e:
            print("Error occured while posting poll!!\n\n e")
            return False
            
    def post_and_db_insert(self,channel_id):
        try:
            response = self.post(channel_id=channel_id)
            self.ts = response.get('ts')
            channel = response.get('channel')
            self.event_datetime
            payload = {
                "ts":self.ts,
                "channel":channel,
                "event_date":self.event_datetime,
                "users":[],
                "poll_closed":False
            }
            self.db_insert(payload)
            return True
        except Exception as e:
            print("Error occured while posting poll and its db insertion!!\n\n e")
    


#--------------------------------------------------------------------------------



def generate_token(user_id,ts,secret_data):
    payload = {
        "user_id": user_id,
        "ts":ts,
        "secret_data": secret_data        
    }
    token = jwt.encode(payload,JWT_SECRET_KEY,algorithm='HS256')
    encoded_token = base64.urlsafe_b64encode(token.encode())
    decoded_token = encoded_token.decode()
    print(decoded_token)
    return decoded_token


def generate_qr_code(link,channel_id):
    features = qrcode.QRCode(version=1,box_size=40,border=2)
    features.add_data(link)
    features.make(fit=True)

    generate_image = features.make_image(fill_color="black",back_color="white")
    #generate_image = qrcode.make("QR code for lunch")

    generate_image.save(f'{channel_id}.png')




def decode_token(encoded_token):
    # Decode the Base64 URL encoded token
    decoded_token = base64.urlsafe_b64decode(encoded_token)
    
    # Verify and decode the JWT token using the secret key
    try:
        payload = jwt.decode(decoded_token, JWT_SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        # Handle expired token
        return None
    except jwt.InvalidTokenError:
        # Handle invalid token
        return None



#token = generate_token("SJBSJB456",165165.165,"shell")
#link = f"https://30e6-103-141-56-118.ngrok-free.app/poll/verify/{token}"

#generate_qr_code(link)
#print(decode_token(link))
