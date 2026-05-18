import urllib.request, urllib.error
req = urllib.request.Request('http://127.0.0.1:8000/caepy/api/v1/auth/otp/request', data=b'{"mobile_number":"9999999999"}', headers={'Content-Type': 'application/json'})
try:
    print(urllib.request.urlopen(req).read())
except urllib.error.HTTPError as e:
    print('Error:', e.code, e.read())
