import os
import requests
import json
from dotenv import load_dotenv
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import logging
from tqdm import tqdm

# Load environment variables
load_dotenv()
LLM_FOUNDRY_TOKEN = os.getenv("LLM_FOUNDRY_TOKEN")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("board_member_search.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

class BoardMemberVerifier:
    def __init__(self, input_csv_path):
        self.input_csv_path = input_csv_path
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.visited_urls = set()
        self.max_pages_per_site = 50
        self.rate_limit_delay = 1  # seconds between requests
        
    def load_csv_data(self):
        """Load the input CSV file into a pandas DataFrame"""
        try:
            df = pd.read_csv(self.input_csv_path)
            logger.info(f"Successfully loaded {len(df)} records from {self.input_csv_path}")
            return df
        except Exception as e:
            logger.error(f"Error loading CSV file: {e}")
            raise

    def get_existing_board_members(self, website_url, df):
        """Get existing board members for a specific website from the DataFrame"""
        site_data = df[df['Website URL'] == website_url]
        existing_members = []
        
        for _, row in site_data.iterrows():
            if pd.notna(row['First Name']) and pd.notna(row['Last Name']):
                member = {
                    'First Name': row['First Name'],
                    'Last Name': row['Last Name'],
                    'Title': row['Title'] if pd.notna(row['Title']) else '',
                    'Biography': row['Biography'] if pd.notna(row['Biography']) else ''
                }
                existing_members.append(member)
                
        return existing_members

    def search_for_board_members(self, website_url):
        """Search for board members using LLM Foundry API"""
        system_prompt = """
        You are a research assistant specialized in finding information about company board members and advisory boards.
        Your task is to extract information about board members and advisors from company websites and related sources.
        
        For each board member or advisor found, provide the following information in a structured JSON format:
        1. First Name
        2. Last Name
        3. Title (e.g., Board Member, Advisory Board Member, Director, etc.)
        4. Biography or description (if available)
        5. Source URL where this information was found
        
        Example output format:
        {
            "board_members": [
                {
                    "First Name": "John",
                    "Last Name": "Doe",
                    "Title": "Board Member",
                    "Biography": "John has 20 years of experience in the industry...",
                    "Source": "https://example.com/about-us"
                }
            ],
            "advisory_members": [
                {
                    "First Name": "Jane",
                    "Last Name": "Smith",
                    "Title": "Advisory Board Member",
                    "Biography": "Jane is an expert in...",
                    "Source": "https://example.com/advisors"
                }
            ],
            "status": "success|not_found",
            "message": "Additional information about the search results"
        }
        """
        
        message_prompt = f"""
        Please extract the board of directors and board of advisors from the following website: {website_url}.
        Focus on extracting information directly from the website's pages and linked resources. 
        Only include individuals explicitly identified as board members or advisors. 
        Do not include members of the leadership or management team unless they are also on the board or advisory board.
        
        If the website does not have a clear board of directors or advisors page, search for news articles, press releases, 
        or blog posts on the website that might mention board members or advisors.
        
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
            response.raise_for_status()
            data = response.json()
            
            # Extract the response text
            if 'candidates' in data and len(data['candidates']) > 0 and 'content' in data['candidates'][0] and 'parts' in data['candidates'][0]['content'] and len(data['candidates'][0]['content']['parts']) > 0:
                parsable_output = data['candidates'][0]['content']['parts'][0]['text']
                # Clean up the JSON string
                json_string = parsable_output.replace('```json', '').replace('```', '').replace('\\', '').strip()
                
                try:
                    json_output = json.loads(json_string)
                    return json_output
                except json.JSONDecodeError as e:
                    logger.error(f"JSONDecodeError: {e}")
                    logger.error(f"Problematic JSON string: {json_string}")
                    return {"status": "error", "message": f"Failed to parse JSON: {str(e)}"}
            else:
                logger.error("Unexpected response structure from LLM Foundry API.")
                return {"status": "error", "message": "Unexpected response structure from API"}
                
        except requests.exceptions.RequestException as e:
            logger.error(f"RequestException: {e}")
            return {"status": "error", "message": f"API request failed: {str(e)}"}
        except json.JSONDecodeError as e:
            logger.error(f"JSONDecodeError: {e}")
            return {"status": "error", "message": f"Failed to parse API response: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    def filter_new_members(self, all_members, existing_members):
        """Filter out members that already exist in the dataset"""
        new_members = []
        
        for member in all_members:
            # Check if this member already exists
            is_existing = False
            for existing in existing_members:
                # Compare first and last names (case-insensitive)
                if (member.get('First Name', '').lower() == existing.get('First Name', '').lower() and
                    member.get('Last Name', '').lower() == existing.get('Last Name', '').lower()):
                    is_existing = True
                    break
            
            if not is_existing:
                new_members.append(member)
                
        return new_members

    def process_website(self, website_url, df):
        """Process a single website to find board members"""
        logger.info(f"Processing website: {website_url}")
        
        # Get existing board members for this website
        existing_members = self.get_existing_board_members(website_url, df)
        logger.info(f"Found {len(existing_members)} existing members for {website_url}")
        
        # Search for board members using the LLM API
        search_result = self.search_for_board_members(website_url)
        
        # Extract board members and advisory members
        all_members = []
        if 'board_members' in search_result and isinstance(search_result['board_members'], list):
            all_members.extend(search_result['board_members'])
        if 'advisory_members' in search_result and isinstance(search_result['advisory_members'], list):
            all_members.extend(search_result['advisory_members'])
        
        # Filter out members that already exist
        new_members = self.filter_new_members(all_members, existing_members)
        logger.info(f"Found {len(new_members)} new members for {website_url}")
        
        # Generate feedback on the model's performance
        feedback = ""
        if len(new_members) > 5:
            feedback = "POOR"
        elif len(new_members) > 0:
            feedback = "AVERAGE"
        else:
            feedback = "GOOD"
        
        return {
            'website_url': website_url,
            'new_members': new_members,
            'feedback': feedback,
            'search_status': search_result.get('status', 'unknown')
        }

    def update_csv_with_new_members(self, df, results):
        """Update the DataFrame with newly found board members"""
        new_rows = []
        
        for result in results:
            website_url = result['website_url']
            new_members = result['new_members']
            
            for member in new_members:
                # Create a new row with the same structure as the original DataFrame
                new_row = {col: '' for col in df.columns}
                new_row['Website URL'] = website_url
                new_row['Status'] = 'BOM Available'
                new_row['Comments'] = 'Added by automated search'
                new_row['First Name'] = member.get('First Name', '')
                new_row['Last Name'] = member.get('Last Name', '')
                new_row['Title'] = member.get('Title', '')
                new_row['Title Source'] = member.get('Source', '')
                new_row['Biography'] = member.get('Biography', '')
                new_row['Biography Source'] = member.get('Source', '')
                
                new_rows.append(new_row)
        
        # Add new rows to the DataFrame
        if new_rows:
            new_df = pd.DataFrame(new_rows)
            updated_df = pd.concat([df, new_df], ignore_index=True)
            return updated_df
        
        return df

    def save_feedback_to_csv(self, results):
        """Save model feedback to a separate CSV file with rating"""
        feedback_data = []
        
        for result in results:
            feedback_text = result['feedback']
            
            feedback_data.append({
                'Website URL': result['website_url'],
                'Search Status': result.get('search_status', 'unknown'),
                'New Members Found': len(result['new_members']),
                'Feedback': feedback_text
            })
        
        feedback_df = pd.DataFrame(feedback_data)
        feedback_df.to_csv(self.feedback_csv_path, index=False)
        logger.info(f"Saved model feedback to {self.feedback_csv_path}")

    def run(self):
        """Run the board member verification process"""
        logger.info("Starting board member verification process")
        
        # Load the input CSV data
        df = self.load_csv_data()
        
        # Get unique website URLs
        website_urls = df['Website URL'].unique()
        logger.info(f"Found {len(website_urls)} unique websites to process")
        
        # Process websites in parallel
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Create a list of future tasks
            future_to_url = {executor.submit(self.process_website, url, df): url for url in website_urls}
            
            # Process results as they complete with a progress bar
            for future in tqdm(future_to_url, desc="Processing websites"):
                url = future_to_url[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing {url}: {e}")
                    # Add a placeholder result with error information
                    results.append({
                        'website_url': url,
                        'new_members': [],
                        'feedback': f"Error processing website: {str(e)}",
                        'search_status': 'error'
                    })
        
        # Update the DataFrame with new members
        updated_df = self.update_csv_with_new_members(df, results)
        
        # Save the updated DataFrame to CSV
        updated_df.to_csv(self.output_csv_path, index=False)
        logger.info(f"Saved enhanced board members to {self.output_csv_path}")
        
        # Save feedback to a separate CSV file
        self.save_feedback_to_csv(results)
        
        # Log summary
        total_new_members = sum(len(result['new_members']) for result in results)
        logger.info(f"Process completed. Found {total_new_members} new board members across {len(website_urls)} websites.")
        
        return {
            'total_websites': len(website_urls),
            'total_new_members': total_new_members,
            'output_file': self.output_csv_path,
            'feedback_file': self.feedback_csv_path
        }