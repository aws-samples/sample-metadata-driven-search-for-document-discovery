import streamlit as st
import boto3
import json
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
import pandas as pd

def clean_json_string(response_text):
    """Clean and extract valid JSON from the response"""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx != -1 and end_idx != 0:
                json_str = response_text[start_idx:end_idx]
                return json.loads(json_str)
        except:
            st.error(f"Failed to parse JSON: {response_text}")
            return None

def process_query(input_text):
    try:
        # Initialize Bedrock client
        bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name='us-east-1'
        )

        # Build request payload
        payload = {
            "modelId": "anthropic.claude-3-sonnet-20240229-v1:0",
            "contentType": "application/json",
            "accept": "application/json",
            "body": {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "system": """"Act as an Opensearch DQL writer. Generate queries in exact JSON format following this template:
                            {\"bool\": {\"must\": [{\"term\": {\"FIELD_NAME\": BOOLEAN_VALUE}},{\"exists\": {\"field\": \"company\"}},{\"script\": {\"script\": {\"source\": \"doc['company.keyword'].value.length() > 0\"}}}]}}

                            Available fields and their trigger words:
                            - breach_notification_required (triggered by: notification, breach, security incident)
                            - types_of_expenses (triggered by: expense, cost, fee, charge)
                            - time_entry_requirements (triggered by: time, hour, billing, timekeeper)
                            - company (text)
                            - AMAZON_BEDROCK_TEXT (text)

                            Field mapping rules:
                            1. If input contains 'notification', 'breach', or 'security' → use 'breach_notification_required'
                            2. If input contains 'expense', 'cost', 'fee', or 'charge' → use 'types_of_expenses'
                            3. If input contains 'time', 'hour', 'billing', or 'timekeeper' → use 'time_entry_requirements'

                            Boolean value rules:
                            - Use true if the question is asking about presence/requirements
                            - Use false if the question includes 'not' or asks about absence

                            The query should:
                            1. Always include the company existence check
                            2. Always include the company keyword length validation
                            3. Use term queries for boolean fields
                            4. Return only the JSON query with no additional text or explanation

                            Example inputs and outputs:
                            Input: 'what are the breach notification requirements?'
                            Output: {\"bool\": {\"must\": [{\"term\": {\"breach_notification_required\": true}},{\"exists\": {\"field\": \"company\"}},{\"script\": {\"script\": {\"source\": \"doc['company.keyword'].value.length() > 0\"}}}]}}

                            Input: 'what are not the time entry requirements?'
                            Output: {\"bool\": {\"must\": [{\"term\": {\"time_entry_requirements\": false}},{\"exists\": {\"field\": \"company\"}},{\"script\": {\"script\": {\"source\": \"doc['company.keyword'].value.length() > 0\"}}}]}}"
                            """,
                "messages": [
                    {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": "what are the breach notification requirements for each client?"
                        }
                    ]
                },
                {
                    "role": "assistant", 
                    "content": [
                        {
                            "type": "text",
                            "text": "{\"bool\": {\"must\": [{\"term\": {\"breach_notification_required\": true}},{\"exists\": {\"field\": \"company\"}},{\"script\": {\"script\": {\"source\": \"doc['company.keyword'].value.length() > 0\"}}}]}}"
                        }
                    ]
                },
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "text",
                            "text": input_text
                        }
                    ]
                }
                ]
            }
        }

        with st.spinner('Generating query...'):
            # Convert payload to bytes and invoke model
            body_bytes = json.dumps(payload["body"]).encode('utf-8')
            response = bedrock_runtime.invoke_model(
                body=body_bytes,
                contentType=payload["contentType"],
                accept=payload["accept"],
                modelId=payload["modelId"]
            )

            # Parse response
            response_body = response['body'].read().decode('utf-8')
            response_json = json.loads(response_body)
            search_query = response_json['content'][0]['text']

            # Clean and parse the search query
            cleaned_query = clean_json_string(search_query)
            if not cleaned_query:
                st.error("Failed to parse valid JSON from the response")
                return

        with st.spinner('Searching documents...'):
            # OpenSearch configuration
            #host = 's1p88b1drjo7uhddya4a.us-east-1.aoss.amazonaws.com'
            ssm_client = boto3.client('ssm', region_name='us-east-1')
            host = ssm_client.get_parameter(Name='/kb/opensearchEndpoint')['Parameter']['Value']
            region = 'us-east-1'
            service = 'aoss'
            credentials = boto3.Session().get_credentials()
            auth = AWSV4SignerAuth(credentials, region, service)

            # Initialize OpenSearch client
            client = OpenSearch(
                hosts=[{'host': host, 'port': 443}],
                http_auth=auth,
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection,
                pool_maxsize=20
            )

            # Prepare and execute search query
            query = {
                'size': 10000,
                "_source": [
                    "company",
                    "breach_notification_required",
                    "Agreement_date",
                    "time_entry_requirements",
                    "types_of_expenses",
                    "AMAZON_BEDROCK_TEXT",
                    "x-amz-bedrock-kb-source-uri"
                ],
                'query': cleaned_query,
                "aggs": {
                    "unique_companies": {
                        "terms": {
                            "field": "company.keyword",
                            "size": 10000
                        }
                    }
                }
            }

            response = client.search(
                body=query,
                index='bedrock-knowledge-base-default-index'
            )

            return response

    except Exception as e:
        st.error(f"Error occurred: {str(e)}")
        return None

def main():
    st.set_page_config(page_title="Anycompany Document Search", layout="wide")
    
    st.title("Anycompany Document Search")
    
    # Initialize session state for query_text if it doesn't exist
    if 'query_text' not in st.session_state:
        st.session_state.query_text = ""

    # Input section
    st.subheader("Search Query")
    query_text = st.text_area(
        "Enter your search query:",
        value=st.session_state.query_text,
        placeholder="Example: what are the breach notification requirements for each client?",
        height=100,
        key="query_input"
    )

    # Add example queries as buttons
    st.write("Example queries:")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("Breach Notification Requirements"):
            st.session_state.query_text = "what are the breach notification requirements for each client?"
            st.rerun()
            
    with col2:
        if st.button("Time Entry Requirements"):
            st.session_state.query_text = "what are the time entry requirements for each client?"
            st.rerun()
            
    with col3:
        if st.button("Types of Expenses"):
            st.session_state.query_text = "what are the types of expenses requirements for each client?"
            st.rerun()

    with col4:
        if st.button("Clear", type="secondary"):
            st.session_state.query_text = ""
            st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Search", type="primary"):
            if query_text:
                response = process_query(query_text)
                
                if response:
                    # Display results in a nice format
                    st.subheader("Search Results")
                    
                    # Create tabs for different views
                    tab1, tab2 = st.tabs(["Summary View", "Detailed View"])
                    
                    with tab1:
                        # Summary view with company aggregations
                        companies = response['aggregations']['unique_companies']['buckets']
                        if companies:
                            st.write(f"Found results for {len(companies)} companies")
                            df = pd.DataFrame(companies)
                            st.dataframe(df)
                        else:
                            st.write("No companies found")

                    with tab2:
                        # Detailed view with all documents
                        hits = response['hits']['hits']
                        if hits:
                            for hit in hits:
                                source = hit['_source']
                                with st.expander(f"Company: {source.get('company', 'Unknown')}"):
                                    st.write("Agreement Date:", source.get('Agreement_date', 'N/A'))
                                    st.write("Breach Notification:", source.get('breach_notification_required', 'N/A'))
                                    st.write("Time Entry Requirements:", source.get('time_entry_requirements', 'N/A'))
                                    st.write("Types of Expenses:", source.get('types_of_expenses', 'N/A'))
                                    st.write("Full Text:", source.get('AMAZON_BEDROCK_TEXT', 'N/A'))
                                    # Add a "View Source" button for the full text
                                    #if st.button("View Source", key=hit['_id']):
                                    #    st.text_area("Full Text", source.get('AMAZON_BEDROCK_TEXT', 'No text available'),
                                    #               height=200)
                        else:
                            st.write("No detailed results found")
            else:
                st.warning("Please enter a search query")

if __name__ == "__main__":
    main()
