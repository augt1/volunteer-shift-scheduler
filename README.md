# Volunteer Scheduler

## Importing Volunteers from Google Sheets

To import volunteers from a Google Sheet, follow these steps:

1. Set up Google Sheets API:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Sheets API
   - Create credentials (OAuth 2.0 Client ID)
   - Download the credentials and save as `credentials.json` in the project root

2. Prepare your Google Sheet:
   Required columns:
   - "Name" - Volunteer's first name
   - "Surname" - Volunteer's last name
   - "Email" - Used as unique identifier
   - "Mobile phone number" - Will be formatted automatically:
     - Numbers starting with "00" will have "00" replaced with "+"
     - Numbers without "+" will have "+30" added
   - "processed in application" - Only "yes" entries will be imported
   - "position" - Will be matched to existing positions

3. Get your spreadsheet ID and range:
   - Spreadsheet ID is in the URL: `https://docs.google.com/spreadsheets/d/`**`spreadsheetId`**`/edit`
   - Range is like "Sheet1!A2:F" (A2:F will get columns A through F, starting from row 2)

4. Run the import command:
```bash
python manage.py import_volunteers <spreadsheet_id> <range>
```

Example:
```bash
python manage.py import_volunteers "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" "Sheet1!A2:F"
```

The first time you run the command, it will open a browser window for Google OAuth authentication. After authenticating, the credentials will be saved in `token.json` for future use.

### Features:
- Automatically formats phone numbers
- Assigns positions if they match existing position names
- Only imports volunteers marked as "yes" in "processed in application"
- Updates existing volunteers if email matches
- Creates new volunteers if email is new
