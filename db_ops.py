from abc import ABC
from db_config import db
from slack_sdk import WebClient
from dotenv import load_dotenv
from datetime import datetime
from random_word import RandomWords
import os

bot_token = os.environ.get("SLACK_ENTRI_LUNCH_BOT_TOKEN")
lunch_channel_id = os.environ.get("ENTRI_LUNCH_CHANNEL_ID")

client = WebClient(bot_token)


class DbOpsInterface(ABC):
    def db_details():
        pass

    def db_exists():
        pass

    def db_update():
        pass

    def db_destroy():
        pass


class DBOps(DbOpsInterface):
    def __init__(self,collection):
        self.collection = collection

    def db_insert(self,data):
        try:
            print("inside db_insert")
            result = self.collection.insert_one(data)
            return result
        except Exception as e:
            print(f"Error occured while inserting data to db\n{e}")
        
    
    def db_details(self,slack_id):
        try:
            result = self.collection.find({"slack_id":slack_id})
            return result
        except Exception as e:
            print(f"Error occured while fetching data from db\n{e}")
    
    
    def db_exists(self,slack_id):
        try:
            user = self.collection.find({"id":slack_id})
            return True if user else False
        except Exception as e:
            print(f"Error occured while fetching data from db\n{e}")

    def db_update(self,filter,updated_data):
        try:
            print(filter)
            print(updated_data)
            result = self.collection.update_one(filter,{"$set":updated_data})
            return result
        except Exception as e:
            print(f"Error occured while updating data to db\n{e}")

    
    def db_destroy(self,slack_id):
        try:
            result = self.collection.delete_one({"slack_id":slack_id})
            return result
        except Exception as e:
            print(f"Error occured while deleting data from db\n{e}")




class User(DBOps):
    def __init__(self,collection):
        super().__init__(collection)

    
class Channel(DBOps):
    def __init__(self,channel_id,collection):
        self.channel_id = channel_id
        super().__init__(collection)

    
    def get_all_channel_members(self):
        request = client.conversations_members(channel=self.channel_id)
        if request['ok']:
            return request['members']

    def set_all_members_to_db(self):     #use this method only when db is empty or there will be duplicate data
        members_list = self.get_all_channel_members()
        for slack_id in members_list:
            user_profile = client.users_profile_get(user=slack_id).data.get("profile")
            if 'bot_id' in user_profile:
                continue
            payload = {
                "name":user_profile.get("real_name"),
                "slack_id":slack_id,
                "email":user_profile.get("email"),
                "image":user_profile.get("image_192")
            }        
            self.db_create(payload)

    
class PollDB(DBOps):
    def __init__(self,collection):
        super().__init__(collection=collection)

    def get_poll_count(self,ts):
        pipeline = [
                {"$match": {'ts': ts}},
                {"$project": {"event_date":1,"count": {"$size": "$users"}}}
        ]
        try:
            poll_cursor = self.collection.aggregate(pipeline)
            for item in poll_cursor:
                return item.get("count")
        except Exception as e:
            print(f"An error occurred during count: {e}")


    def get_polled_users(self, ts):
        pipeline = [
            {"$match": {"ts": ts}},
            {"$unwind": "$users"},  # Unwind to access each poll individually
            {"$project": {"_id":0,"slack_id": "$users.slack_id","secret_data":"$users.secret_data"}}  # Project only the slack_id field
        ]
        try:
            polled_users = self.collection.aggregate(pipeline)
            return [{'user_id':user['slack_id'],'secret_data':user['secret_data']} for user in polled_users]  # Extract slack_id from the result
        except Exception as e:
            print(f"An error occurred during fetching polled_users: {e}")


    def poll_yes(self, slack_id, ts):
        random_words = RandomWords()
        word = random_words.get_random_word()
        payload = {
            'slack_id': slack_id,
            'polled_date': datetime.now(),
            'secret_data': word,
            'verified': False
        }
        try:
            result = self.collection.update_one(
                            {'ts': ts,
                             'poll_closed':False,
                             'users.slack_id': {'$ne': slack_id}
                            },
                            {'$addToSet': {'users': payload}}
            )
            print("result",result)
        except Exception as e:
            print(f"Error occurred while updating date to poll_history\n{e}")



    def poll_no(self, slack_id, ts):
        try:
            # Find the document to update
            result = self.collection.update_one(
                        {'ts': ts,
                         'poll_closed':False,
                         'users': {'$elemMatch': {'slack_id': slack_id}}
                        },
                        {'$pull': {'users': {'slack_id': slack_id}}}
            )

        except Exception as e:
            print(f"Error occurred while updating document: {e}")


    def verify_poll(self,payload):
        slack_id = payload.get("user_id")
        ts = payload.get("ts")
        secret_data = payload.get("secret_data")
        if not (slack_id and ts and secret_data):
            return None      
        query = {
            "ts": ts,
            "users": {
                "$elemMatch":{
                    "slack_id":slack_id,
                    "verified":False
            }},
            "poll_closed": True, 
        }        
        projection = {"users.$": 1}

        result = self.collection.find_one(query,projection)

        if result:
            update_query = {
                "$set": {
                    "users.$.verified": True
                }
            }
            self.collection.update_one(query, update_query)
            return result
        return None