import smtplib
from email.message import EmailMessage

try:
    msg = EmailMessage()
    msg.set_content('Test email from python')
    msg['Subject'] = 'Test SMTP'
    msg['From'] = 'rgtvertex.ai@outlook.com'
    msg['To'] = 'rgtvertex.ai@outlook.com'

    server = smtplib.SMTP('smtp-mail.outlook.com', 587)
    server.set_debuglevel(1)
    server.starttls()
    server.login('rgtvertex.ai@outlook.com', 'adnmyouhdewrlhcc')
    server.send_message(msg)
    server.quit()
    print('SUCCESS')
except Exception as e:
    print('ERROR:', e)
