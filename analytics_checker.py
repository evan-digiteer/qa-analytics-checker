import os
import json
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from jinja2 import Environment, FileSystemLoader
import time
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

ANALYTICS_TOOLS = {
    'Google Tag Manager': {
        'url_patterns': [
            'googletagmanager.com/gtm.js',
            'googletagmanager.com/ns'
        ]
    },
    'Google Analytics 4': {
        'url_patterns': [
            'google-analytics.com/g/collect',
            'analytics.google.com/g/collect',
            'googletagmanager.com/gtag/js?id=G-'
        ]
    },
    'Universal Analytics': {
        'url_patterns': [
            'google-analytics.com/analytics.js',
            'google-analytics.com/collect',
            'stats.g.doubleclick.net'
        ]
    },
    'Meta Pixel': {
        'url_patterns': [
            'connect.facebook.net/signals',
            'facebook.com/tr/',
            'connect.facebook.net/en_US/fbevents.js'
        ]
    },
    'Hotjar': {
        'url_patterns': [
            'hotjar.com/api',
            'vars.hotjar.com',
            'static.hotjar.com/c'
        ]
    },
    'LinkedIn Insight': {
        'url_patterns': [
            'snap.licdn.com/li.lms-analytics',
            'platform.linkedin.com'
        ]
    },
    'TikTok Pixel': {
        'url_patterns': [
            'analytics.tiktok.com/i18n/pixel',
            'analytics.tiktok.com/api'
        ]
    },
    'Twitter Pixel': {
        'url_patterns': [
            'static.ads-twitter.com/uwt.js',
            'analytics.twitter.com'
        ]
    },
    'Microsoft Ads': {
        'url_patterns': [
            'bat.bing.com/bat.js',
            'clarity.ms'
        ]
    },
    'Google Ads': {
        'url_patterns': [
            'googleadservices.com/pagead',
            'google.com/pagead',
            'googleads.g.doubleclick.net'
        ]
    }
}

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Set logging preferences in options instead of desired_capabilities
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def get_network_requests(driver):
    try:
        logs = driver.get_log('performance')
        network_requests = []
        for entry in logs:
            try:
                log = json.loads(entry['message'])['message']
                if 'Network.requestWillBeSent' == log['method']:
                    req = {
                        'url': log['params']['request']['url'],
                        'method': log['params']['request']['method'],
                        'timestamp': log['params']['timestamp'],
                        'headers': log['params']['request'].get('headers', {}),
                        'type': log['params']['type'] if 'type' in log['params'] else 'Other'
                    }
                    network_requests.append(req)
            except:
                continue
        return network_requests
    except Exception as e:
        print(f"Warning: Could not get network logs: {str(e)}")
        return []

def get_script_snippet(content, pattern, max_length=300):
    import re
    # Find the relevant portion of the script
    content_lines = content.split('\n')
    for line_num, line in enumerate(content_lines):
        if pattern in line:
            # Get 3 lines before and after for context
            start = max(0, line_num - 3)
            end = min(len(content_lines), line_num + 4)
            snippet = '\n'.join(content_lines[start:end])
            if len(snippet) > max_length:
                snippet = snippet[:max_length] + '...'
            return snippet
    return None

def check_analytics(url):
    driver = setup_driver()
    results = {}
    all_requests = []
    
    try:
        driver.get(url)
        start_time = datetime.now()
        time.sleep(5)
        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        
        requests = get_network_requests(driver)
        
        # Check each analytics tool
        for tool_name, tool_data in ANALYTICS_TOOLS.items():
            matching_requests = []
            
            for req in requests:
                if any(pattern in req['url'] for pattern in tool_data['url_patterns']):
                    matching_requests.append(req)
            
            results[tool_name] = {
                'found': len(matching_requests) > 0,
                'details': f"Found {len(matching_requests)} matching requests" if matching_requests else None,
                'confidence': 'High' if matching_requests else 'None',
                'requests': matching_requests,
                'timing': {
                    'scan_start': start_time.strftime('%H:%M:%S'),
                    'duration': str(datetime.now() - start_time)
                }
            }

        # Add other analytics
        other_analytics = [
            req for req in requests 
            if any(term in req['url'].lower() for term in ['analytics', 'pixel', 'track', 'collect', 'stats'])
            and not any(pattern in req['url'] for tool in ANALYTICS_TOOLS.values() for pattern in tool['url_patterns'])
        ]
        
        if other_analytics:
            results['Other Analytics'] = {
                'found': True,
                'details': f"Found {len(other_analytics)} unknown analytics requests",
                'confidence': 'Medium',
                'requests': other_analytics,
                'timing': {
                    'scan_start': start_time.strftime('%H:%M:%S'),
                    'duration': str(datetime.now() - start_time)
                }
            }

    finally:
        driver.quit()
    
    return results

def generate_report(url, results):
    # Create reports directory if it doesn't exist
    reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
    os.makedirs(reports_dir, exist_ok=True)

    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template('report.html')
    
    report_data = {
        'url': url,
        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'results': results
    }
    
    # Generate timestamped filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'analytics_report_{timestamp}.html'
    report_path = os.path.join(reports_dir, filename)
    
    report_html = template.render(report_data)
    with open(report_path, 'w') as f:
        f.write(report_html)
    
    return report_path

def main():
    load_dotenv()
    url = os.getenv('WEBSITE_URL')
    
    if not url:
        print("Error: WEBSITE_URL not found in .env file")
        return
    
    print(f"Checking analytics for: {url}")
    results = check_analytics(url)
    report_path = generate_report(url, results)
    print(f"Report generated: {report_path}")

if __name__ == "__main__":
    main()
