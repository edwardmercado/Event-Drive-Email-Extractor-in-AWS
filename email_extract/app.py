import json
import datetime
import email, imaplib
import boto3, botocore
import pandas as pd
import csv, os

imap_url = 'imap.gmail.com'
email_mailbox = "INBOX"
s3_bucket = os.environ['S3_BUCKET']
ssm_email_username = os.environ['SSM_EMAIL_USERNAME']
ssm_email_password = os.environ['SSM_EMAIL_PWD']

s3_resource = boto3.resource('s3')
s3_client = boto3.client('s3')

ssm_client = boto3.client('ssm')

def lambda_handler(event, context):

    #get email and username from SSM Parameter Store
    email_username_parameter = ssm_client.get_parameter(Name=ssm_email_username)
    email_password_parameter = ssm_client.get_parameter(Name=ssm_email_password)
    
    email_username = email_username_parameter['Parameter']['Value']
    email_password = email_password_parameter['Parameter']['Value']

    is_login(email_username, email_password)

def is_login(email_username, email_pwd):
    # create an IMAP4 class with SSL 
    imap = imaplib.IMAP4_SSL(imap_url)

    #authenticate
    try:
        imap.login(email_username, email_pwd)
    except Exception as e:
        print(f"Unable to login due to {e}")
        return False
    else:
        print("Login successfully")
        extract_mail(imap, email_mailbox)
        return True

def extract_mail(imap, mailbox):
    imap.select('inbox')
    data = imap.search(None, 'ALL')
    mail_ids = data[1]
    id_list = mail_ids[0].split()   
    first_email_id = int(id_list[0])
    latest_email_id = int(id_list[-1])

    try:
        s3_resource.Object(s3_bucket, 'emails.csv').load()
    except botocore.exceptions.ClientError as e:

        if e.response['Error']['Code'] == "404":
            # The object does not exist.
            print("Excel file not found.. Initial Insert")
            #create csv
            create_csv()
            #insert initial values
            initial_insert(imap, latest_email_id, first_email_id)
            #store to s3
    else:
        df1 = pd.read_csv('s3://'+ s3_bucket + '/emails.csv')
        last_email_id_from_csv = df1.iloc[-1]['Email ID']
        
        print(f"last email id from csv: {last_email_id_from_csv}")
        print(f"latest email id from gmail: {latest_email_id}")
        #compare
        if latest_email_id != last_email_id_from_csv:
            #append data
            update_insert(imap, last_email_id_from_csv, latest_email_id)
        else:
            #dont append anything
            print("Nothing is inserted")

def create_csv():
    print("Creating excel file...")
    with open('/tmp/emails.csv', 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Email ID", "FROM", "SUBJECT", "DATE"])

def append_to_csv(email_ids, email_from, email_subject, email_date):
    with open('/tmp/emails.csv', 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([email_ids, email_from, email_subject, email_date])

def return_last_row(imap):
    pass

def sort_csv():
    #sort data fram by Email ID
    data_frame = pd.read_csv("/tmp/emails.csv")
    data_frame.sort_values(by=['Email ID'], inplace=True)

    #print(data_frame)
    data_frame.to_csv("/tmp/emails.csv", index=False)
    print("File sorted by Email ID")


def initial_insert(imap, latest_email_id, starting_id):
    for email_ids in range(latest_email_id, starting_id, -1):
            raw_data = imap.fetch(str(email_ids), '(RFC822)' )
            
            for response_part in raw_data:
                arr = response_part[0]
                if isinstance(arr, tuple):

                    msg = email.message_from_string(str(arr[1],'utf-8'))
                    email_subject = msg['subject']
                    email_from = msg['from']
                    email_date = msg['Date']

                    append_to_csv(email_ids, email_from, email_subject, email_date)

    sort_csv()
    print("Inserted initial data from your email")
    upload_to_s3()
    
                    

def update_insert(imap, starting_id, latest_email_id):
    for email_ids in range(latest_email_id, starting_id, -1):
            raw_data = imap.fetch(str(email_ids), '(RFC822)' )
            
            for response_part in raw_data:
                arr = response_part[0]
                if isinstance(arr, tuple):

                    msg = email.message_from_string(str(arr[1],'utf-8'))
                    email_subject = msg['subject']
                    email_from = msg['from']
                    email_date = msg['Date']

                    append_to_csv(email_ids, email_from, email_subject, email_date)

    sort_csv()
    print("Inserted new data")
    upload_to_s3()


def upload_to_s3():
    try:
        response = s3_client.upload_file("/tmp/emails.csv", s3_bucket, "emails.csv")
    except Exception as e:
        print(f"Unable to upload to s3, ERROR: {e}")
        return False
    else:
        print("Uploaded file to s3")
        return True