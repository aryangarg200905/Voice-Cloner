import torch
from TTS.api import TTS
import boto3
import textwrap
from pydub import AudioSegment
from pydub.utils import which
from pymongo import MongoClient
import time
import fastapi

AudioSegment.converter = which("ffmpeg")
AudioSegment.ffprobe = which("ffprobe")

device = "cuda" if torch.cuda.is_available() else "cpu"
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
s3 = boto3.client('s3', endpoint_url='http://localhost:4566', aws_access_key_id='dummy', aws_secret_access_key='dummy')
bucket_name = 'my-local-bucket'
s3.create_bucket(Bucket=bucket_name)

def split_text(text, max_length=400):
    return textwrap.wrap(text, max_length)

def generate_audio(audios,projects):
    while True:
        document = audios.find_one({}, sort=[('id', 1)])
        if document:
            audios.update_one({"_id": document['_id']},{"$set": {"status": "1"}})
            audio_id = document['user_id']
            language = document['language'].upper()
            text = document['text']
            
            name = document['voice_id'].lower()
            list_of_languages = ["ENGLISH", "HINDI"]
            if len(text.strip()) == 0 or audio_id <= 0 or len(language.strip()) == 0:
                document2 = projects.find_one({'user_id':audio_id})
                projects.update_one({"_id":document2['_id'] },{"$set": {"audio_link": "Error: One or more requirements not provided"}})
                audios.delete_one({'_id':document['_id']})
                continue
            if language not in list_of_languages:
                document2 = projects.find_one({'user_id':audio_id})
                projects.update_one({"_id": document2['_id']},{"$set": {"audio_link": "Error: Language not available to be cloned"}})
                audios.delete_one({'_id':document['_id']})
                continue
            audios.update_one({"_id": document['_id']},{"$set": {"status": "2"}})
            if language == "ENGLISH":
                language = "en"
            else:
                language = "hi"
            audio = f"{name}.mp3"
            output_files = []

            for idx, chunk in enumerate(split_text(text)):
                output_file_path = f"output_{idx}.mp3"
                tts.tts_to_file(text=chunk, speaker_wav=audio, language=language, file_path=output_file_path)
                output_files.append(output_file_path)
    
            merged = AudioSegment.empty()
            for output_file_path in output_files:
                audio_segment = AudioSegment.from_file(output_file_path)
                merged += audio_segment
    
            merged_output_path = "output.mp3"
            merged.export(merged_output_path, format="mp3")
            audios.update_one({"_id": document['_id']},{"$set": {"status": "3"}})
            bucket_name = 'my-local-bucket'
            object_name = 'output.mp3'

            s3.upload_file(merged_output_path, bucket_name, object_name)
            file_url = s3.generate_presigned_url('get_object', Params={'Bucket': bucket_name, 'Key': object_name}, ExpiresIn=3600)
            document2 = projects.find_one({'user_id':audio_id})
            projects.update_one({"_id": document2['_id']},{"$set": {"audio_link": file_url}})
            projects.update_one({"_id": document2['_id']},{"$set": {"edit_flag": document2['edit_flag']+1}})
            audios.update_one({"_id": document['_id']},{"$set": {"status": "4"}})
            audios.delete_one({'_id':document['_id']})
        else:
            time.sleep(15)

client = MongoClient('mongodb://127.0.0.1:27017/')
collection = client['voiceCloning']['inputs']
collection_2 = client['voiceCloning']['projects']
generate_audio(collection,collection_2)



