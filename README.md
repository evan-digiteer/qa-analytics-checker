# Analytics Checker

A Python tool that detects analytics and tracking tools on websites by monitoring actual network requests.

## Features

### Supported Analytics Tools
- Google Tools
  - Google Tag Manager (GTM)
  - Google Analytics 4 (GA4)
  - Universal Analytics (UA)
  - Google Ads / Remarketing
- Social Media
  - Meta (Facebook) Pixel
  - TikTok Pixel
  - Twitter Pixel
  - LinkedIn Insight
- Marketing & UX
  - Microsoft Ads / Clarity
  - Hotjar
  - Other unknown analytics (automatically detected)

### Capabilities
- Detects actual analytics requests (not just script presence)
- Monitors network traffic for tracking calls
- Generates detailed HTML reports with:
  - Request information (URLs, methods, headers)
  - Confidence levels
  - Timing information
  - Unknown analytics detection

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your environment:
   ```bash
   cp .env.example .env
   ```
4. Edit `.env` and set `WEBSITE_URL`

## Usage

Run the script:
```bash
python analytics_checker.py
```

Reports are generated in the `reports` directory with timestamps:
```
reports/analytics_report_YYYYMMDD_HHMMSS.html
```

## Requirements

- Python 3.7+
- Chrome browser installed
- Internet connection

## Notes

- The tool uses Selenium WebDriver in headless mode
- Detection is based on actual network requests
- Some sites may require longer scan times for full detection