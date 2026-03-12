import requests
import os

url = "http://127.0.0.1:8000/accounts/login/"
client = requests.session()
client.get(url)
csrftoken = client.cookies['csrftoken']

login_data = dict(username='student@warhawks.ulm.edu', password='password123', csrfmiddlewaretoken=csrftoken, next='/')
r = client.post(url, data=login_data, headers={"Referer": url})

print(r.status_code)
