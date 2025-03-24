import requests
import json
import os
from dotenv import load_dotenv
import csv

# Load environment variables
load_dotenv()
LLM_FOUNDRY_TOKEN = os.getenv("LLM_FOUNDRY_TOKEN")

# Define system prompt
system_prompt = """
## You are a helpful assistant helping to find details about the board of directors and board of advisors of a given website. You need to extract information about each member and provide it in a structured format.

# Instructions:
1.  **Identify Board Members and Advisors:** Scrape the provided website and its linked pages to identify members of the board of directors and board of advisors. Prioritize information found directly on the website. Do not include members of leadership or management teams unless they are explicitly identified as board members or advisors.
2.  **Search Thoroughly:** If you can't find board information on main pages, look for news articles, press releases, or blog posts on the website that might mention board members or advisors.
3.  **Extract Details:** For each member, extract the following details if available on the website or linked profiles (e.g., LinkedIn):
    *   First Name
    *   Last Name
    *   Title
    *   Phone
    *   Phone Type
    *   Phone Source
    *   Email
    *   Email Source
    *   LinkedIn URL
    *   Biography
    *   Biography Source
    *   Designation
    *   Undergrad College
    *   Undergrad Year
    *   Postgrad College
    *   Postgrad Year
    *   Metro Area
    *   Mailing Street
    *   Mailing City
    *   Mailing State/Province
    *   Mailing Zip/Postal Code
    *   Mailing Country
4.  **Name Handling:**  Do not include "Dr." in the first name.  Do not include "PhD" or "MD" in the last name.  Extract the core first and last name.
5.  **Handle Missing Information:** If a piece of information is not available, leave the corresponding field blank.
6.  **Provide Sources:**  Note the source URL for each piece of information (e.g., website, LinkedIn).
7.  **Focus on Accuracy:** Ensure the extracted information is accurate. Do not make up information or use example data from this prompt.
8.  **Output Format:** Return the data in a JSON format suitable for conversion to a CSV file, following the structure below.
9.  **No Results:** If no board members or advisors can be found after thorough searching, return a JSON with a single entry indicating "No board members found" in the Status field.

# Output Format:
```json
[
    {
        "Status": "BOM Available",
        "Comments": "Board of Directors",
        "First Name": "John",
        "Last Name": "Smith",
        "Title": "Member Board Of Directors",
        "Title Source": "https://example.com/about-us/",
        "Phone": "",
        "Phone Type": "",
        "Phone Source": "",
        "Email": "",
        "Email Source": "",
        "LinkedIn URL": "https://www.linkedin.com/in/john-smith/",
        "Biography": "John Smith is an experienced executive...",
        "Biography Source": "https://example.com/about-us/",
        "Designation": "MBA",
        "Undergrad College": "Harvard University",
        "Undergrad Year": "1995",
        "Postgrad College": "",
        "Postgrad Year": "",
        "Metro Area": "Boston",
        "Mailing Street": "",
        "Mailing City": "Boston",
        "Mailing State/Province": "Massachusetts",
        "Mailing Zip/Postal Code": "",
        "Mailing Country": "United States"
    }
]
```

If no board members are found, return:
```json
[
    {
        "Status": "No board members found",
        "Comments": "No information available about board of directors or advisors on the website"
    }
]
```
"""

def process_board_members(website_url):
    message_prompt = f""" Please extract the board of directors and board of advisors from the following website: {website_url}.
    Focus on extracting information directly from the website's pages and linked resources. Only include individuals explicitly identified as board members or advisors. Do not include members of the leadership or management team unless they are also on the board or advisory board.
    If the website does not have a clear board of directors or advisors page, search for news articles, press releases, or blog posts on the website that might mention board members or advisors.
    Do not use the example data from the system prompt as actual output. Only return real data found on the website.
    If after thorough searching you cannot find any board members or advisors, indicate this clearly in your response.
    """

    try:
        response = requests.post(
            "https://llmfoundry.straive.com/gemini/v1beta/models/gemini-2.0-flash-001:generateContent",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {LLM_FOUNDRY_TOKEN}:my-test-project"},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": message_prompt}]}],
                "generationConfig": {"temperature": 0},
                "tools": [{"google_search": {}}]
            }
        )
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        if 'candidates' in data and len(data['candidates']) > 0 and 'content' in data['candidates'][0] and 'parts' in data['candidates'][0]['content'] and len(data['candidates'][0]['content']['parts']) > 0:
            parsable_output = data['candidates'][0]['content']['parts'][0]['text']
            json_string = parsable_output.replace('```json', '').replace('```', '').replace('\\', '').strip()

            try:
                json_output = json.loads(json_string)
            except json.JSONDecodeError as e:
                print(f"JSONDecodeError: {e}")
                print(f"Problematic JSON string")
                return None
        else:
            print("Unexpected response structure from LLM Foundry API.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"RequestException: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")
        print(f"Response data: {data}")
        return None
    except KeyError as e:
        print(f"KeyError: {e}")
        print(f"Response data: {data}")
        return None

    return json_output

def save_to_csv(data, website_url, csv_file_path, write_header=True):
    if not data:
        print("No data to save.")
        return

    # Add website URL to each record
    for record in data:
        record["Website URL"] = website_url

    # Ensure Website URL is the first column
    if "Website URL" in data[0]:
        fieldnames = ["Website URL"] + [field for field in data[0].keys() if field != "Website URL"]
    else:
        fieldnames = data[0].keys()

    try:
        file_exists = os.path.isfile(csv_file_path) and os.path.getsize(csv_file_path) > 0
        
        with open(csv_file_path, 'a', newline='', encoding='utf-8') as csvfile:  # Open in append mode
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if write_header and not file_exists:
                writer.writeheader()  # Write header only if it's a new file
            writer.writerows(data)

        print(f"Data successfully written to CSV file: {csv_file_path}")

    except Exception as e:
        print(f"Error writing to CSV file: {e}")