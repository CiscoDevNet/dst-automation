FROM python:3

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update
RUN apt-get install -y traceroute

COPY . .

CMD [ "./automate_dst.sh" ]
