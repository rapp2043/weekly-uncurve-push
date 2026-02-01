# Un:Curve Newsletter Engine

Automated weekly newsletter generator that creates Malcolm Gladwell-style content using AI, then publishes to Make.com for distribution via Brevo.

## How It Works

1. **Scout** - Searches the web for counter-intuitive, surprising headlines
2. **Braider** - AI selects the most "Gladwellian" headline based on the Davis Index
3. **Writer** - Generates a full newsletter article with narrative structure
4. **Publish** - Sends the final HTML to Make.com webhook for Brevo distribution

## Automated Schedule

The GitHub Action runs automatically at **8:00 AM EST (13:00 UTC) every Sunday**.

Each weekly edition is a flagship deep dive: 1500-2000 words with layered narratives, interwoven anecdotes, and rich historical parallels.

## Manual Trigger

You can manually trigger the workflow:

1. Go to the **Actions** tab in your GitHub repository
2. Select **Weekly Newsletter**
3. Click **Run workflow**

## Setup

### 1. Fork/Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

### 2. Configure GitHub Secrets

Go to **Settings > Secrets and variables > Actions** and add:

| Secret | Description |
|--------|-------------|
| `DEEPSEEK_API_KEY` | Your DeepSeek API key for AI generation |
| `MAKE_WEBHOOK_URL` | Your Make.com webhook URL |

### 3. Update Image URLs

Edit `templates/email_template.html` and replace the placeholder URLs:

```html
<!-- Replace USERNAME/REPO with your actual GitHub username and repository name -->
https://raw.githubusercontent.com/USERNAME/REPO/main/assets/logo.png
https://raw.githubusercontent.com/USERNAME/REPO/main/assets/signature.png
```

### 4. Set Up Make.com Scenario

1. Create a new scenario in Make.com
2. Add a **Webhooks > Custom Webhook** trigger
3. Copy the webhook URL and add it to GitHub Secrets as `MAKE_WEBHOOK_URL`
4. Add a **Brevo > Send an Email** module
5. Map the fields:
   - **Subject**: `{{1.subject}}`
   - **HTML Content**: `{{1.html_content}}`
   - **To**: Your Brevo contact list

## Project Structure

```
├── .github/
│   └── workflows/
│       └── weekly-newsletter.yml   # GitHub Actions workflow
├── assets/
│   ├── logo.png                    # Newsletter logo
│   └── signature.png               # Author signature
├── config/
│   ├── 01_MASTER_VOICE.md          # Writing style guide
│   ├── 02_DAVIS_INDEX.md           # Headline selection criteria
│   └── GLADWELL_NEWSLETTER_SYSTEM.md  # Full system prompt
├── drafts/                         # Archived newsletters
├── templates/
│   └── email_template.html         # HTML email template
├── gladwell_engine.py              # Main engine script
├── headline_history.json           # Tracks used headlines
├── requirements.txt                # Python dependencies
└── README.md
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DEEPSEEK_API_KEY="your-api-key"
export MAKE_WEBHOOK_URL="your-webhook-url"

# Run the engine
python gladwell_engine.py
```

## Webhook Payload

The engine sends a JSON payload to Make.com:

```json
{
  "subject": "Newsletter Subject Line",
  "html_content": "<html>...</html>",
  "send_date": "2026-01-31",
  "metadata": {
    "headline": "Original headline title",
    "davis_pattern": "D3",
    "source_url": "https://..."
  }
}
```

## License

Private project - Un:Curve Newsletter by Anthony Clemons
