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
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
import re
import logging

ANALYTICS_TOOLS = {
    'Google Tag Manager': {
        'url_patterns': [
            'googletagmanager.com/gtm.js',
            'googletagmanager.com/ns'
        ],
        'dom_patterns': [
            '//script[contains(@src, "googletagmanager.com/gtm.js")]',
            '//iframe[contains(@src, "googletagmanager.com/ns")]'
        ],
        'script_patterns': [
            'gtm.start',
            'dataLayer'
        ],
        'global_vars': ['dataLayer', 'google_tag_manager']
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

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('analytics_checker.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

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

def check_dom_elements(driver, patterns):
    found_elements = []
    for xpath in patterns:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
            found_elements.extend(elements)
        except Exception as e:
            logging.warning(f"Error checking DOM element {xpath}: {str(e)}")
    return found_elements

def check_global_variables(driver, variables):
    found_vars = []
    for var in variables:
        try:
            result = driver.execute_script(f"return typeof window['{var}'] !== 'undefined'")
            if result:
                found_vars.append(var)
        except Exception as e:
            logging.warning(f"Error checking global variable {var}: {str(e)}")
    return found_vars

def analyze_script_content(driver):
    script_contents = {}
    try:
        scripts = driver.find_elements(By.TAG_NAME, "script")
        for script in scripts:
            try:
                content = script.get_attribute('innerHTML')
                if content:
                    script_contents[script.get_attribute('src') or 'inline'] = content
            except:
                continue
    except Exception as e:
        logging.warning(f"Error analyzing script content: {str(e)}")
    return script_contents

def calculate_confidence(tool_results):
    score = 0
    if tool_results.get('network_requests', []):
        score += 0.4
    if tool_results.get('dom_elements', []):
        score += 0.3
    if tool_results.get('global_vars', []):
        score += 0.2
    if tool_results.get('script_matches', []):
        score += 0.1
    
    if score >= 0.7:
        return 'High'
    elif score >= 0.4:
        return 'Medium'
    elif score > 0:
        return 'Low'
    return 'None'

def get_implementation_details(driver, script_contents, tool_data, matching_requests):
    implementations = {
        'script_snippets': [],
        'network_calls': [],
        'dom_elements': []
    }
    
    # Get script implementation snippets
    if 'script_patterns' in tool_data:
        for src, content in script_contents.items():
            for pattern in tool_data['script_patterns']:
                snippet = get_script_snippet(content, pattern)
                if snippet:
                    implementations['script_snippets'].append({
                        'source': src,
                        'pattern': pattern,
                        'code': snippet
                    })

    # Get network call details
    for req in matching_requests:
        implementations['network_calls'].append({
            'url': req['url'],
            'method': req['method'],
            'headers': {k: v for k, v in req['headers'].items() if 'cookie' not in k.lower()}
        })

    # Get DOM implementations
    if 'dom_patterns' in tool_data:
        elements = check_dom_elements(driver, tool_data['dom_patterns'])
        for element in elements:
            try:
                outer_html = element.get_attribute('outerHTML')
                if outer_html:
                    implementations['dom_elements'].append(outer_html[:500])  # Limit size
            except:
                continue

    return implementations

def wait_for_page_load(driver, timeout=30):
    """Wait for all dynamic content to load"""
    try:
        # Wait for document ready state
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # Wait for jQuery (if present)
        jquery_ready = """
        return (typeof jQuery === 'undefined') || (jQuery.active === 0 && document.readyState === 'complete')
        """
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(jquery_ready)
        )
        
        # Wait for AJAX requests to complete
        ajax_complete = """
        return (typeof jQuery === 'undefined') || (jQuery.active === 0)
        """
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script(ajax_complete)
        )
        
        return True
    except TimeoutException:
        logging.warning("Timeout waiting for page load, continuing anyway...")
        return False

def simulate_user_interaction(driver):
    """Simulate user interaction to trigger dynamic content"""
    try:
        # Scroll in steps
        total_height = driver.execute_script("return document.body.scrollHeight")
        viewport_height = driver.execute_script("return window.innerHeight")
        current_position = 0
        
        while current_position < total_height:
            driver.execute_script(f"window.scrollTo(0, {current_position});")
            current_position += viewport_height // 2  # Scroll half viewport at a time
            time.sleep(1)  # Wait between scrolls
        
        # Scroll back to top
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        
        # Click any cookie consent buttons (common in analytics)
        consent_button_selectors = [
            "//button[contains(translate(., 'ACEPTED', 'acepted'), 'accept')]",
            "//button[contains(translate(., 'COOKIES', 'cookies'), 'cookies')]",
            "//a[contains(translate(., 'ACCEPT', 'accept'), 'accept')]"
        ]
        
        for selector in consent_button_selectors:
            try:
                buttons = driver.find_elements(By.XPATH, selector)
                for button in buttons:
                    if button.is_displayed():
                        button.click()
                        time.sleep(1)
            except:
                continue
        
    except Exception as e:
        logging.warning(f"Error during user interaction simulation: {str(e)}")

def check_analytics(url):
    logger = setup_logging()
    driver = setup_driver()
    results = {}
    
    try:
        logger.info(f"Starting analysis of {url}")
        driver.get(url)
        
        # Initial wait for page load
        wait_for_page_load(driver)
        
        # Simulate user interaction
        simulate_user_interaction(driver)
        
        # Additional wait for analytics to load
        time.sleep(5)
        
        # Get all detection data
        network_requests = get_network_requests(driver)
        script_contents = analyze_script_content(driver)
        
        for tool_name, tool_data in ANALYTICS_TOOLS.items():
            tool_results = {
                'network_requests': [],
                'dom_elements': [],
                'script_matches': [],
                'global_vars': []
            }
            
            # Check network requests
            tool_results['network_requests'] = [
                req for req in network_requests
                if any(pattern in req['url'] for pattern in tool_data['url_patterns'])
            ]
            
            # Check DOM elements
            if 'dom_patterns' in tool_data:
                tool_results['dom_elements'] = check_dom_elements(driver, tool_data['dom_patterns'])
            
            # Check global variables
            if 'global_vars' in tool_data:
                tool_results['global_vars'] = check_global_variables(driver, tool_data['global_vars'])
            
            # Check script content
            if 'script_patterns' in tool_data:
                for content in script_contents.values():
                    if any(pattern in content for pattern in tool_data['script_patterns']):
                        tool_results['script_matches'].append(True)
            
            # Calculate confidence and combine results
            confidence = calculate_confidence(tool_results)
            
            implementations = get_implementation_details(
                driver,
                script_contents,
                tool_data,
                tool_results['network_requests']
            )
            
            results[tool_name] = {
                'found': any(len(v) > 0 for v in tool_results.values()),
                'confidence': confidence,
                'details': {
                    'network_requests': len(tool_results['network_requests']),
                    'dom_elements': len(tool_results['dom_elements']),
                    'script_matches': len(tool_results['script_matches']),
                    'global_vars': tool_results['global_vars']
                },
                'raw_data': tool_results,
                'implementations': implementations
            }
            
            logger.info(f"Analyzed {tool_name}: Found = {results[tool_name]['found']}, Confidence = {confidence}")
    
    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
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
