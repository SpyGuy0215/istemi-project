from openrouter import OpenRouter
from dotenv import load_dotenv
import csv
import io
import os
import time
import requests
from datetime import timedelta
from urllib.parse import quote


# Load env vars from vars.env file (root directory)
load_dotenv(dotenv_path="src/vars.env")
HCAI_API_KEY = os.getenv("HCAI_API_KEY")
AI_PROMPT = os.getenv("ANALYZATION_PROMPT", "Analyze this telemetry data.")
PROMETHEUS_BASE_URL = "https://prometheus-prod-56-prod-us-east-2.grafana.net"
DATAPOINT_COUNT = int(os.getenv("PROMETHEUS_DATAPOINT_COUNT", "100"))
QUERY_STEP_SECONDS = int(os.getenv("PROMETHEUS_QUERY_STEP_SECONDS", "100"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SUPABASE_RESPONSES_TABLE = os.getenv("SUPABASE_RESPONSES_TABLE", "ai_responses")


def fetch_prometheus_range_data(base_url, datapoint_count, step_seconds):
    r = requests.get(PROMETHEUS_BASE_URL+"/api/prom/api/v1/labels", auth=(os.getenv("PROMETHEUS_UID"), os.getenv("PROMETHEUS_API_TOKEN")))
    print("Prometheus API response status:", r.status_code)

    # get the list of all metric names
    r = requests.get(PROMETHEUS_BASE_URL+"/api/prom/api/v1/label/__name__/values", auth=(os.getenv("PROMETHEUS_UID"), os.getenv("PROMETHEUS_API_TOKEN")))
    print("Prometheus API response status:", r.status_code)
    metric_names = r.json().get("data", [])[:7]
    print(f"Found {len(metric_names)} metrics in Prometheus.")
    print("Sample metric names:", metric_names)

    # for the metric names, fetch the last month of data with the specified step
    end_time = int(time.time())
    start_time = end_time - int(timedelta(days=10).total_seconds())
    print(f"Querying Prometheus for data from {time.ctime(start_time)} to {time.ctime(end_time)} with step {step_seconds}s...")
    all_values = []
    for metric in metric_names:
        r = requests.get(
            f"{PROMETHEUS_BASE_URL}/api/prom/api/v1/query_range",
            params={
                "query": metric,
                "start": start_time,
                "end": end_time,
                "step": step_seconds,
            },
            auth=(os.getenv("PROMETHEUS_UID"), os.getenv("PROMETHEUS_API_TOKEN"))
        )
        r.raise_for_status()
        print(r.json()["data"]["result"])
        values = r.json()["data"]['result'][0]['values']
        # filter out the values where the value is 0
        filtered_values = []
        for value in values:
            if float(value[1]) != 0:
                filtered_values.append(value)
        all_values.append(filtered_values)
    print(f'Fetched data for {len(all_values)} metrics, with {datapoint_count} datapoints.')

    return metric_names, all_values

def turn_data_to_csv(metric_names, data):
    # take the data for individual metrics and make it so that every timestamp has values for all the metrics

    aligned_data = {}
    for metric_values in data:
        for timestamp, value in metric_values:
            timestamp = round(timestamp / 10) * 10  # round to nearest 10
            if timestamp not in aligned_data:
                aligned_data[timestamp] = {}
            metric_index = data.index(metric_values)
            aligned_data[timestamp][f"metric_{metric_index}"] = value 


    # convert the aligned data to csv
    output = io.StringIO()
    writer = csv.writer(output)
    # write the header with timestamp and metric names
    header = ["timestamp"] + metric_names
    writer.writerow(header)
    # write the rows
    for timestamp, metrics in aligned_data.items():
        row = [timestamp] + [metrics.get(f"metric_{i}", "") for i in range(len(data))]
        writer.writerow(row)
    csv_text = output.getvalue()
    print("Converted data to CSV format.")

    return csv_text

def build_message_with_inline_csv(prompt, csv_text):
    # turn it into one message with the prompt and the csv text
    message = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "\n\nHere is the CSV data:\n\n" + csv_text}
    ]
    return message


def save_response_to_supabase(model, response_code, response, success):
    if not SUPABASE_URL or not SUPABASE_API_KEY:
        print("Supabase env vars are missing. Skipping Supabase insert.")
        return

    table_path = quote(SUPABASE_RESPONSES_TABLE, safe="")
    endpoint = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table_path}"

    payload = {
        "model": model,
        "response_code": response_code,
        "response": response,
        "success": success,
    }

    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=20)
        if resp.ok:
            print(f"Saved response for {model} to Supabase.")
        else:
            print(f"Failed to save {model} response to Supabase: {resp.status_code} {resp.text}")
    except requests.RequestException as exc:
        print(f"Error while saving {model} response to Supabase: {exc}")


def send_model_request(client, model_name, messages):
    try:
        response = client.chat.send(
            model=model_name,
            messages=messages,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str):
            content = str(content)

        print(content)
        save_response_to_supabase(
            model=model_name,
            response_code="ok",
            response=content,
            success=True,
        )
    except Exception as exc:
        error_message = str(exc)
        print(f"Model request failed for {model_name}: {error_message}")
        save_response_to_supabase(
            model=model_name,
            response_code="error",
            response=error_message,
            success=False,
        )



def main():
    print("HCAI_API_KEY loaded:", HCAI_API_KEY is not None)
    print(
        f"Fetching about the last {DATAPOINT_COUNT} datapoints "
        f"per metric (step={QUERY_STEP_SECONDS}s)..."
    )

    # Fetch range data from Prometheus API
    metric_names, data = fetch_prometheus_range_data(PROMETHEUS_BASE_URL, DATAPOINT_COUNT, QUERY_STEP_SECONDS)
    # turn into csv
    csv_text = turn_data_to_csv(metric_names, data)

    client = OpenRouter(
        api_key=HCAI_API_KEY,
        server_url="https://ai.hackclub.com/proxy/v1",
    )

    messages = build_message_with_inline_csv(AI_PROMPT, csv_text)
    send_model_request(client, "google/gemini-3-flash-preview", messages)
    send_model_request(client, "qwen/qwen3-next-80b-a3b-instruct", messages)


if __name__ == "__main__":
    main()