# GTA World Property Bot 🏠

A Discord bot that tracks and notifies about property listings from the GTA World map. The bot monitors houses, apartments, businesses, office leases, and storage units, providing real-time notifications and various commands to search and view available properties.

## Features 🌟

- **Real-time Property Tracking**: Automatically fetches and monitors property listings every 10 minutes
- **Multiple Property Types**: Tracks various property categories:
  - Houses
  - Apartments
  - Businesses
  - Office Leases
  - Storage Units
- **Instant Notifications**: Sends notifications to a designated channel when new properties are listed
- **Rich Search Features**: Search properties by type and price range
- **Market Statistics**: View current market overview and statistics
- **Pagination Support**: Browse through large property lists with ease
- **Persistent Storage**: Saves property data between bot restarts

## Requirements 📋

- Python 3.8 or higher
- Chrome/Chromium browser (for web scraping)
- Discord Bot Token
- Server with permissions to:
  - Send messages
  - Send embeds
  - Add reactions
  - Manage messages (for pagination)

### Data Storage

The bot automatically creates a `property_data` directory to store JSON files for each property type:

- `houses.json`
- `apartments.json`
- `businesses.json`
- `office_leases.json`
- `storage_units.json`

## Commands 🎮

### General Property Listings

| Command       | Description                   |
| ------------- | ----------------------------- |
| `/houses`     | List all available houses     |
| `/apartments` | List all available apartments |
| `/businesses` | List all available businesses |

### Rental Properties

| Command            | Description                  |
| ------------------ | ---------------------------- |
| `/rentals office`  | List available office leases |
| `/rentals storage` | List available storage units |
| `/rentals all`     | Show all rental properties   |

### Search and Statistics

| Command                              | Description                            |
| ------------------------------------ | -------------------------------------- |
| `/search min_price max_price [type]` | Search properties within a price range |
| `/stats`                             | Show current market statistics         |

### Search Types

When using the `/search` command, you can specify the following types:

- `houses`
- `apartments`
- `businesses`
- `office`
- `storage`
- `all` (default)

## Features in Detail 📝

### Property Notifications

- The bot automatically sends notifications to the specified channel when new properties are listed
- Notifications include:
  - Property type and price
  - Address/location
  - Coordinates
  - Custom formatting for rental properties (monthly price)

### Market Statistics

The `/stats` command provides:

- Total number of listings per category
- Average prices
- Lowest and highest prices
- Market overview

### Pagination

- Property listings are paginated (10 items per page)
- Navigate using reaction buttons:
  - ◀️ Previous page
  - ▶️ Next page
- Auto-timeout after 60 seconds of inactivity

## Error Handling and Logging 📝

The bot includes comprehensive error handling and logging:

- Logs are written to console with timestamp and log level
- Errors are caught and logged appropriately
- Failed property fetches are handled gracefully

## Credits 👏

ME.

## Support 💬

For support, please contact the developer of this bot.

## Disclaimer ⚠️

This bot is unofficial and not affiliated with GTA World.
