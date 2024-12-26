import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import undetected_chromedriver as uc
import re
from typing import Dict
import os
from dotenv import load_dotenv
import platform
import logging
import traceback
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('PropertyBot')

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_IDS = [int(guild_id.strip()) for guild_id in os.getenv('GUILD_IDS', '').split(',') if guild_id.strip()]
NOTIFICATION_GUILD_ID = int(GUILD_IDS[0]) if GUILD_IDS else None
NOTIFICATION_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID')) if os.getenv('NOTIFICATION_CHANNEL_ID') else None

def validate_env_variables():
    """Validate required environment variables"""
    missing_vars = []
    
    if not DISCORD_TOKEN:
        missing_vars.append('DISCORD_TOKEN')
    
    if not GUILD_IDS:
        logger.warning("No GUILD_IDS specified - bot will sync commands globally")
    
    if not NOTIFICATION_CHANNEL_ID:
        logger.warning("No NOTIFICATION_CHANNEL_ID specified - notifications will be disabled")
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

class PropertyBot(commands.Bot):
    def __init__(self):
        try:
            # Initialize intents
            intents = discord.Intents.default()
            intents.message_content = True
            super().__init__(command_prefix='/', intents=intents)
            
            # Create data directory if it doesn't exist
            self.data_dir = 'property_data'
            os.makedirs(self.data_dir, exist_ok=True)
            
            # Property types
            self.property_types = ['houses', 'apartments', 'businesses', 'office_leases', 'storage_units']
            
            # Initialize properties and previous properties
            self.properties = {prop_type: [] for prop_type in self.property_types}
            self.previous_properties = {prop_type: [] for prop_type in self.property_types}
            
            # Load data from separate files
            self.load_all_properties()
            
        except Exception as e:
            logger.error(f"Error initializing bot: {e}")
            raise

    def get_file_path(self, property_type: str) -> str:
        """Get the file path for a specific property type."""
        return os.path.join(self.data_dir, f'{property_type}.json')

    def load_property_file(self, property_type: str) -> list:
        """Load properties from a specific JSON file."""
        file_path = self.get_file_path(property_type)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Error loading {property_type}.json")
                return []
        return []

    def save_property_file(self, property_type: str, data: list):
        """Save properties to a specific JSON file."""
        file_path = self.get_file_path(property_type)
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(data)} {property_type} to file")
        except Exception as e:
            logger.error(f"Error saving {property_type}.json: {e}")

    def load_all_properties(self):
        """Load all property files."""
        for prop_type in self.property_types:
            self.properties[prop_type] = self.load_property_file(prop_type)
            self.previous_properties[prop_type] = self.properties[prop_type].copy()
            logger.info(f"Loaded {len(self.properties[prop_type])} {prop_type} from file")

    def save_all_properties(self):
        """Save all property files."""
        for prop_type in self.property_types:
            self.save_property_file(prop_type, self.properties[prop_type])

    def validate_residential_property(self, property_data):
        """Validate residential property data"""
        try:
            if len(property_data) < 5:
                return None
                
            # Validate and convert each field
            property_id = str(property_data[0]).strip()
            address = str(property_data[1]).strip()
            
            try:
                price = int(property_data[2])
                if price <= 0:
                    logger.warning(f"Invalid price for property {property_id}: {price}")
                    return None
            except (ValueError, TypeError):
                logger.warning(f"Invalid price format for property {property_id}: {property_data[2]}")
                return None
                
            try:
                x_coord = float(property_data[3])
                y_coord = float(property_data[4])
            except (ValueError, TypeError):
                logger.warning(f"Invalid coordinates for property {property_id}: {property_data[3]}, {property_data[4]}")
                return None
                
            return {
                'id': property_id,
                'address': address,
                'price': price,
                'coords': [x_coord, y_coord]
            }
            
        except Exception as e:
            logger.error(f"Error validating residential property: {e}")
            return None

    def validate_business_property(self, business_data):
        """Validate business property data"""
        try:
            if len(business_data) < 7:
                return None
                
            # Validate and convert each field
            business_id = str(business_data[0]).strip()
            name = str(business_data[3]).strip()  # Business name is in index 3
            
            try:
                price = int(business_data[2])
                if price <= 0:
                    logger.warning(f"Invalid price for business {business_id}: {price}")
                    return None
            except (ValueError, TypeError):
                logger.warning(f"Invalid price format for business {business_id}: {business_data[2]}")
                return None
                
            try:
                x_coord = float(business_data[5])  # Coordinates are in index 5 and 6
                y_coord = float(business_data[6])
            except (ValueError, TypeError):
                logger.warning(f"Invalid coordinates for business {business_id}: {business_data[5]}, {business_data[6]}")
                return None
                
            return {
                'id': business_id,
                'address': name,
                'price': price,
                'coords': [x_coord, y_coord]
            }
            
        except Exception as e:
            logger.error(f"Error validating business property: {e}")
            return None

    async def fetch_residential_properties(self, driver):
        """Fetch residential properties (houses and apartments) from 4sale.php"""
        try:
            driver.get('https://map.gta.world/4sale.php')
            await asyncio.sleep(2)  # Wait for page to load
            html = driver.page_source
            markers_match = re.search(r'var markers = (\[\[.*?\]\]);', html, re.DOTALL)
            
            new_houses = []
            new_apartments = []
            
            if not markers_match:
                logger.error("Could not find markers data in 4sale.php")
                return [], []
                
            try:
                markers_data = json.loads(markers_match.group(1))
                for property in markers_data:
                    property_data = self.validate_residential_property(property)
                    if property_data:
                        # Categorize as apartment or house
                        address_lower = property_data['address'].lower()
                        is_apartment = any(keyword in address_lower for keyword in 
                                         ['unit', 'floor', 'room', 'apartment', 'apt', 'complex'])
                        
                        if is_apartment:
                            new_apartments.append(property_data)
                        else:
                            new_houses.append(property_data)
                            
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing residential markers data: {e}")
                return [], []
                
            logger.info(f"Successfully fetched {len(new_houses)} houses and {len(new_apartments)} apartments")
            return new_houses, new_apartments
            
        except Exception as e:
            logger.error(f"Error fetching residential properties: {e}")
            return [], []

    async def fetch_business_properties(self, driver):
        """Fetch business properties from biz.php"""
        try:
            driver.get('https://map.gta.world/biz.php')
            await asyncio.sleep(2)  # Wait for page to load
            html = driver.page_source
            biz_match = re.search(r'var data = (\[\[.*?\]\]);', html, re.DOTALL)
            
            new_businesses = []
            
            if not biz_match:
                logger.error("Could not find business data in biz.php")
                return []
                
            try:
                biz_data = json.loads(biz_match.group(1))
                for business in biz_data:
                    business_data = self.validate_business_property(business)
                    if business_data:
                        new_businesses.append(business_data)
                        
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing business data: {e}")
                return []
                
            logger.info(f"Successfully fetched {len(new_businesses)} businesses")
            return new_businesses
            
        except Exception as e:
            logger.error(f"Error fetching business properties: {e}")
            return []

    async def fetch_rental_properties(self, driver):
        """Fetch rental properties (office leases and storage units) from 4rent.php"""
        try:
            driver.get('https://map.gta.world/4rent.php')
            await asyncio.sleep(2)  # Wait for page to load
            html = driver.page_source
            rentals_match = re.search(r'var markers = (\[\[.*?\]\]);', html, re.DOTALL)
            
            new_storage_units = []
            new_office_leases = []
            
            if not rentals_match:
                logger.error("Could not find markers data in 4rent.php")
                return [], []
                
            try:
                rentals_data = json.loads(rentals_match.group(1))
                for rental in rentals_data:
                    rental_data = self.validate_residential_property(rental)  # Uses same structure as residential
                    if rental_data:
                        # Categorize as storage unit or office lease
                        address_lower = rental_data['address'].lower()
                        if any(keyword in address_lower for keyword in ['storage', 'container']):
                            new_storage_units.append(rental_data)
                        else:
                            new_office_leases.append(rental_data)
                            
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing rental data: {e}")
                return [], []
                
            logger.info(f"Successfully fetched {len(new_storage_units)} storage units and {len(new_office_leases)} office leases")
            return new_storage_units, new_office_leases
            
        except Exception as e:
            logger.error(f"Error fetching rental properties: {e}")
            return [], []

    async def send_new_property_notification(self, property_data: dict, property_type: str):
        try:
            colors = {
                'houses': discord.Color.green(),
                'apartments': discord.Color.blue(),
                'businesses': discord.Color.gold(),
                'office_leases': discord.Color.purple(),
                'storage_units': discord.Color.orange()
            }
            
            title_prefixes = {
                'houses': 'House',
                'apartments': 'Apartment',
                'businesses': 'Business',
                'office_leases': 'Office Lease',
                'storage_units': 'Storage Unit'
            }
            
            # Validate property data
            required_fields = ['address', 'price', 'coords']
            if not all(field in property_data for field in required_fields):
                logger.error(f"Missing required fields in property data: {property_data}")
                return
                
            if not isinstance(property_data['coords'], list) or len(property_data['coords']) != 2:
                logger.error(f"Invalid coordinates format in property data: {property_data}")
                return
            
            try:
                formatted_price = f"${property_data['price']:,}"
                if property_type in ['office_leases', 'storage_units']:
                    formatted_price += "/month"
            except (ValueError, TypeError):
                logger.error(f"Invalid price format in property data: {property_data}")
                return
            
            embed = discord.Embed(
                title=f"New {title_prefixes[property_type]} Listed! 🏢",
                description=f"A new {property_type.rstrip('s').replace('_', ' ')} has been listed!",
                color=colors.get(property_type, discord.Color.default())
            )
            
            embed.add_field(
                name="Address/Name",
                value=str(property_data['address']),
                inline=False
            )
            
            embed.add_field(
                name="Price" if property_type not in ['office_leases', 'storage_units'] else "Monthly Rent",
                value=formatted_price,
                inline=False
            )
            
            embed.add_field(
                name="Location",
                value=f"Coordinates: {property_data['coords'][0]}, {property_data['coords'][1]}",
                inline=False
            )
            
            if NOTIFICATION_GUILD_ID and NOTIFICATION_CHANNEL_ID:
                try:
                    guild = self.get_guild(NOTIFICATION_GUILD_ID)
                    if not guild:
                        logger.error(f"Cannot find guild with ID {NOTIFICATION_GUILD_ID}")
                        return
                        
                    channel = guild.get_channel(NOTIFICATION_CHANNEL_ID)
                    if not channel:
                        logger.error(f"Cannot find channel with ID {NOTIFICATION_CHANNEL_ID}")
                        return
                    
                    if not channel.permissions_for(guild.me).send_messages:
                        logger.error("Bot doesn't have permission to send messages in notification channel")
                        return
                    
                    await channel.send("@everyone New listing!", embed=embed)
                    logger.info(f"Sent new {property_type} notification")
                    
                except discord.errors.Forbidden:
                    logger.error("Bot doesn't have required permissions in the notification channel")
                except Exception as e:
                    logger.error(f"Error sending notification: {e}")
            else:
                logger.warning("Notification guild ID or channel ID not configured")
                
        except Exception as e:
            logger.error(f"Error creating property notification: {e}")

    @tasks.loop(minutes=10)
    async def fetch_properties(self):
        """Main property fetching task"""
        driver = None
        try:
            logger.info("Starting property fetch...")
            # Store current properties as previous
            for prop_type in self.property_types:
                self.previous_properties[prop_type] = self.properties[prop_type].copy()
            
            options = uc.ChromeOptions()
            if platform.system() == 'Linux':
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
            else:
                options.add_argument('--headless=new')
            
            driver = uc.Chrome(options=options)
            
            # Initialize new properties dictionary
            new_properties = {prop_type: [] for prop_type in self.property_types}
            
            # Fetch all property types
            try:
                new_houses, new_apartments = await self.fetch_residential_properties(driver)
                new_properties['houses'] = new_houses
                new_properties['apartments'] = new_apartments
                
                new_businesses = await self.fetch_business_properties(driver)
                new_properties['businesses'] = new_businesses
                
                new_storage, new_offices = await self.fetch_rental_properties(driver)
                new_properties['storage_units'] = new_storage
                new_properties['office_leases'] = new_offices
                
            except Exception as e:
                logger.error(f"Error during property fetching: {e}")
                return
            
            # Process notifications for new properties
            try:
                notifications_sent = 0
                for property_type in self.property_types:
                    previous_ids = {str(prop['id']) for prop in self.previous_properties[property_type]}
                    current_ids = {str(prop['id']) for prop in new_properties[property_type]}
                    new_ids = current_ids - previous_ids
                    
                    for property_data in new_properties[property_type]:
                        if str(property_data['id']) in new_ids:
                            await self.send_new_property_notification(property_data, property_type)
                            notifications_sent += 1
                            
                logger.info(f"Sent {notifications_sent} new property notifications")
                
            except Exception as e:
                logger.error(f"Error processing property notifications: {e}")
            
            # Update current properties and save to files
            try:
                self.properties = new_properties
                self.save_all_properties()
                logger.info(f"Property fetch completed successfully. Total properties: {sum(len(props) for props in new_properties.values())}")
            except Exception as e:
                logger.error(f"Error saving properties: {e}")
                
        except Exception as e:
            logger.error(f"Error during property fetch: {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logger.error(f"Error closing driver: {str(e)}")

    @fetch_properties.before_loop
    async def before_fetch(self):
        await self.wait_until_ready()

    async def setup_hook(self):
        """Set up the bot's commands and sync them"""
        logger.info("Setting up bot...")
        try:
            # Start the property fetch loop
            self.fetch_properties.start()
            
            # Create the command tree if it doesn't exist
            if not hasattr(self, 'tree'):
                self.tree = app_commands.CommandTree(self)
            
            # Add commands to the tree
            for command in [houses, apartments, businesses, rentals, search, stats]:
                try:
                    self.tree.add_command(command)
                    logger.info(f"Added command: {command.name}")
                except Exception as e:
                    logger.error(f"Error adding command {command.name}: {e}")
            
            # Sync commands
            if GUILD_IDS:
                for guild_id in GUILD_IDS:
                    try:
                        guild = discord.Object(id=guild_id)
                        self.tree.copy_global_to(guild=guild)
                        await self.tree.sync(guild=guild)
                        logger.info(f"Commands synced to guild {guild_id}")
                    except Exception as e:
                        logger.error(f"Error syncing commands to guild {guild_id}: {e}")
            else:
                await self.tree.sync()
                logger.info("Commands synced globally")
                
        except Exception as e:
            logger.error(f"Error in setup_hook: {e}")
            raise

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info("Bot is ready!")

# Command Implementations
@app_commands.command(name="apartments", description="List available apartments")
async def apartments(interaction: discord.Interaction):
    bot = interaction.client
    try:
        logger.info(f"Apartments command used by {interaction.user}")
        await interaction.response.defer()
        
        if not bot.properties['apartments']:
            await interaction.followup.send("No apartments currently available!")
            return
            
        sorted_apts = sorted(bot.properties['apartments'], key=lambda x: x['price'])
        per_page = 10
        page = 1
        total_pages = (len(sorted_apts) + per_page - 1) // per_page
        
        def create_embed(current_page):
            start_idx = (current_page - 1) * per_page
            end_idx = min(start_idx + per_page, len(sorted_apts))
            
            embed = discord.Embed(
                title="Available Apartments",
                color=discord.Color.blue(),
                description=f"Page {current_page} of {total_pages} (Total: {len(sorted_apts)} apartments)"
            )
            
            for apt in sorted_apts[start_idx:end_idx]:
                embed.add_field(
                    name=f"${apt['price']:,}",
                    value=f"{apt['address']} | Coords: {apt['coords'][0]}, {apt['coords'][1]}",
                    inline=False
                )
            
            return embed
        
        message = await interaction.followup.send(embed=create_embed(page))
        
        if total_pages > 1:
            await message.add_reaction("◀️")
            await message.add_reaction("▶️")
            
            def check(reaction, user):
                return (
                    user == interaction.user 
                    and str(reaction.emoji) in ["◀️", "▶️"]
                    and reaction.message.id == message.id
                )
            
            while True:
                try:
                    reaction, user = await bot.wait_for("reaction_add", timeout=60, check=check)
                    
                    if str(reaction.emoji) == "◀️" and page > 1:
                        page -= 1
                    elif str(reaction.emoji) == "▶️" and page < total_pages:
                        page += 1
                    
                    await message.edit(embed=create_embed(page))
                    await message.remove_reaction(reaction, user)
                    
                except asyncio.TimeoutError:
                    break
                except discord.errors.Forbidden:
                    logger.warning("Bot doesn't have permission to remove reactions")
                    break
                
            try:
                await message.clear_reactions()
            except:
                pass
            
    except Exception as e:
        logger.error(f"Error in apartments command: {e}")
        await interaction.followup.send("An error occurred while fetching apartments.")

@app_commands.command(name="houses", description="List available houses")
async def houses(interaction: discord.Interaction):
    bot = interaction.client
    try:
        logger.info(f"Houses command used by {interaction.user}")
        await interaction.response.defer()
        
        if not bot.properties['houses']:
            await interaction.followup.send("No houses currently available!")
            return
            
        sorted_houses = sorted(bot.properties['houses'], key=lambda x: x['price'])
        per_page = 10
        page = 1
        total_pages = (len(sorted_houses) + per_page - 1) // per_page
        
        def create_embed(current_page):
            start_idx = (current_page - 1) * per_page
            end_idx = min(start_idx + per_page, len(sorted_houses))
            
            embed = discord.Embed(
                title="Available Houses",
                color=discord.Color.green(),
                description=f"Page {current_page} of {total_pages} (Total: {len(sorted_houses)} houses)"
            )
            
            for house in sorted_houses[start_idx:end_idx]:
                embed.add_field(
                    name=f"${house['price']:,}",
                    value=f"{house['address']} | Coords: {house['coords'][0]}, {house['coords'][1]}",
                    inline=False
                )
            
            return embed
        
        message = await interaction.followup.send(embed=create_embed(page))
        
        if total_pages > 1:
            await message.add_reaction("◀️")
            await message.add_reaction("▶️")
            
            def check(reaction, user):
                return (
                    user == interaction.user 
                    and str(reaction.emoji) in ["◀️", "▶️"]
                    and reaction.message.id == message.id
                )
            
            while True:
                try:
                    reaction, user = await bot.wait_for("reaction_add", timeout=60, check=check)
                    
                    if str(reaction.emoji) == "◀️" and page > 1:
                        page -= 1
                    elif str(reaction.emoji) == "▶️" and page < total_pages:
                        page += 1
                    
                    await message.edit(embed=create_embed(page))
                    await message.remove_reaction(reaction, user)
                    
                except asyncio.TimeoutError:
                    break
                except discord.errors.Forbidden:
                    logger.warning("Bot doesn't have permission to remove reactions")
                    break
                
            try:
                await message.clear_reactions()
            except:
                pass
            
    except Exception as e:
        logger.error(f"Error in houses command: {e}")
        await interaction.followup.send("An error occurred while fetching houses.")

@app_commands.command(name="businesses", description="List available businesses")
async def businesses(interaction: discord.Interaction):
    bot = interaction.client
    try:
        logger.info(f"Businesses command used by {interaction.user}")
        await interaction.response.defer()
        
        if not bot.properties['businesses']:
            await interaction.followup.send("No businesses currently available!")
            return
            
        sorted_biz = sorted(bot.properties['businesses'], key=lambda x: x['price'])
        per_page = 10
        page = 1
        total_pages = (len(sorted_biz) + per_page - 1) // per_page
        
        def create_embed(current_page):
            start_idx = (current_page - 1) * per_page
            end_idx = min(start_idx + per_page, len(sorted_biz))
            
            embed = discord.Embed(
                title="Available Businesses",
                color=discord.Color.gold(),
                description=f"Page {current_page} of {total_pages} (Total: {len(sorted_biz)} businesses)"
            )
            
            for biz in sorted_biz[start_idx:end_idx]:
                embed.add_field(
                    name=f"${biz['price']:,}",
                    value=f"{biz['address']} | Coords: {biz['coords'][0]}, {biz['coords'][1]}",
                    inline=False
                )
            
            return embed
        
        message = await interaction.followup.send(embed=create_embed(page))
        
        if total_pages > 1:
            await message.add_reaction("◀️")
            await message.add_reaction("▶️")
            
            def check(reaction, user):
                return (
                    user == interaction.user 
                    and str(reaction.emoji) in ["◀️", "▶️"]
                    and reaction.message.id == message.id
                )
            
            while True:
                try:
                    reaction, user = await bot.wait_for("reaction_add", timeout=60, check=check)
                    
                    if str(reaction.emoji) == "◀️" and page > 1:
                        page -= 1
                    elif str(reaction.emoji) == "▶️" and page < total_pages:
                        page += 1
                    
                    await message.edit(embed=create_embed(page))
                    await message.remove_reaction(reaction, user)
                    
                except asyncio.TimeoutError:
                    break
                except discord.errors.Forbidden:
                    logger.warning("Bot doesn't have permission to remove reactions")
                    break
                
            try:
                await message.clear_reactions()
            except:
                pass
            
    except Exception as e:
        logger.error(f"Error in businesses command: {e}")
        await interaction.followup.send("An error occurred while fetching businesses.")

@app_commands.command(name="rentals", description="List available office leases and storage units")
@app_commands.choices(type=[
    app_commands.Choice(name="Office Leases", value="office"),
    app_commands.Choice(name="Storage Units", value="storage"),
    app_commands.Choice(name="All Rentals", value="all")
])
async def rentals(interaction: discord.Interaction, type: str = "all"):
    bot = interaction.client
    try:
        logger.info(f"Rentals command used by {interaction.user} with type {type}")
        await interaction.response.defer()
        
        office_leases = bot.properties['office_leases']
        storage_units = bot.properties['storage_units']
        
        if not office_leases and not storage_units:
            await interaction.followup.send("No rental properties currently available!")
            return
        
        if type == "all":
            embed = discord.Embed(
                title="Available Rental Properties",
                color=discord.Color.purple(),
                description="Current rental listings"
            )
            
            if office_leases:
                sorted_offices = sorted(office_leases, key=lambda x: x['price'])
                embed.add_field(
                    name=f"📊 Office Leases (Total: {len(office_leases)})",
                    value="\n".join([
                        f"${lease['price']:,}/month - {lease['address']} | Coords: {lease['coords'][0]}, {lease['coords'][1]}"
                        for lease in sorted_offices[:5]]) + ("\n\nUse `/rentals office` to see all office leases" if len(office_leases) > 5 else ""),
                    inline=False
                )
                
            if storage_units:
                sorted_storage = sorted(storage_units, key=lambda x: x['price'])
                embed.add_field(
                    name=f"📦 Storage Units (Total: {len(storage_units)})",
                    value="\n".join([
                        f"${unit['price']:,}/month - {unit['address']} | Coords: {unit['coords'][0]}, {unit['coords'][1]}"
                        for unit in sorted_storage[:5]
                    ]) + ("\n\nUse `/rentals storage` to see all storage units" if len(storage_units) > 5 else ""),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        else:
            properties = office_leases if type == "office" else storage_units
            if not properties:
                await interaction.followup.send(f"No {'office leases' if type == 'office' else 'storage units'} currently available!")
                return
                
            title = "Office Leases" if type == "office" else "Storage Units"
            color = discord.Color.purple() if type == "office" else discord.Color.orange()
            
            sorted_props = sorted(properties, key=lambda x: x['price'])
            per_page = 10
            page = 1
            total_pages = (len(sorted_props) + per_page - 1) // per_page
            
            def create_embed(current_page):
                start_idx = (current_page - 1) * per_page
                end_idx = min(start_idx + per_page, len(sorted_props))
                
                embed = discord.Embed(
                    title=f"Available {title}",
                    color=color,
                    description=f"Page {current_page} of {total_pages} (Total: {len(sorted_props)} properties)"
                )
                
                for prop in sorted_props[start_idx:end_idx]:
                    embed.add_field(
                        name=f"${prop['price']:,}/month",
                        value=f"{prop['address']} | Coords: {prop['coords'][0]}, {prop['coords'][1]}",
                        inline=False
                    )
                
                return embed
            
            message = await interaction.followup.send(embed=create_embed(page))
            
            if total_pages > 1:
                await message.add_reaction("◀️")
                await message.add_reaction("▶️")
                
                def check(reaction, user):
                    return (
                        user == interaction.user 
                        and str(reaction.emoji) in ["◀️", "▶️"]
                        and reaction.message.id == message.id
                    )
                
                while True:
                    try:
                        reaction, user = await bot.wait_for("reaction_add", timeout=60, check=check)
                        
                        if str(reaction.emoji) == "◀️" and page > 1:
                            page -= 1
                        elif str(reaction.emoji) == "▶️" and page < total_pages:
                            page += 1
                        
                        await message.edit(embed=create_embed(page))
                        await message.remove_reaction(reaction, user)
                        
                    except asyncio.TimeoutError:
                        break
                    except discord.errors.Forbidden:
                        logger.warning("Bot doesn't have permission to remove reactions")
                        break
                    
                try:
                    await message.clear_reactions()
                except:
                    pass
                
    except Exception as e:
        logger.error(f"Error in rentals command: {e}")
        await interaction.followup.send("An error occurred while fetching rental properties.")

@app_commands.command(name="search", description="Search properties by price range and type")
@app_commands.choices(type=[
    app_commands.Choice(name="Houses", value="houses"),
    app_commands.Choice(name="Apartments", value="apartments"),
    app_commands.Choice(name="Businesses", value="businesses"),
    app_commands.Choice(name="Office Leases", value="office"),
    app_commands.Choice(name="Storage Units", value="storage"),
    app_commands.Choice(name="All Properties", value="all")
])
async def search(interaction: discord.Interaction, min_price: int, max_price: int, type: str = "all"):
    bot = interaction.client
    try:
        logger.info(f"Search command used by {interaction.user} with range {min_price}-{max_price} and type {type}")
        await interaction.response.defer()
        
        results = []
        search_categories = []
        if type == "all":
            search_categories = bot.property_types
        elif type == "office":
            search_categories = ['office_leases']
        elif type == "storage":
            search_categories = ['storage_units']
        else:
            search_categories = [type]
        
        for category in search_categories:
            for prop in bot.properties[category]:
                if min_price <= prop['price'] <= max_price:
                    results.append((category, prop))
        
        if not results:
            await interaction.followup.send(
                f"No properties found between ${min_price:,} and ${max_price:,}" +
                (f" for type: {type}" if type != "all" else "")
            )
            return
        
        results.sort(key=lambda x: x[1]['price'])
        per_page = 10
        page = 1
        total_pages = (len(results) + per_page - 1) // per_page
        
        def create_embed(current_page):
            start_idx = (current_page - 1) * per_page
            end_idx = min(start_idx + per_page, len(results))
            
            embed = discord.Embed(
                title=f"Properties between ${min_price:,} and ${max_price:,}",
                color=discord.Color.blue(),
                description=f"Page {current_page} of {total_pages} (Total: {len(results)} properties)"
            )
            
            for category, prop in results[start_idx:end_idx]:
                if category in ['office_leases', 'storage_units']:
                    price_display = f"${prop['price']:,}/month"
                else:
                    price_display = f"${prop['price']:,}"
                
                embed.add_field(
                    name=f"{category.replace('_', ' ').title()} - {price_display}",
                    value=f"{prop['address']} | Coords: {prop['coords'][0]}, {prop['coords'][1]}",
                    inline=False
                )
            
            return embed
        
        message = await interaction.followup.send(embed=create_embed(page))
        
        if total_pages > 1:
            await message.add_reaction("◀️")
            await message.add_reaction("▶️")
            
            def check(reaction, user):
                return (
                    user == interaction.user 
                    and str(reaction.emoji) in ["◀️", "▶️"]
                    and reaction.message.id == message.id
                )
            
            while True:
                try:
                    reaction, user = await bot.wait_for("reaction_add", timeout=60, check=check)
                    
                    if str(reaction.emoji) == "◀️" and page > 1:
                        page -= 1
                    elif str(reaction.emoji) == "▶️" and page < total_pages:
                        page += 1
                    
                    await message.edit(embed=create_embed(page))
                    await message.remove_reaction(reaction, user)
                    
                except asyncio.TimeoutError:
                    break
                except discord.errors.Forbidden:
                    logger.warning("Bot doesn't have permission to remove reactions")
                    break
                
            try:
                await message.clear_reactions()
            except:
                pass
            
    except Exception as e:
        logger.error(f"Error in search command: {e}")
        await interaction.followup.send("An error occurred while searching properties.")

@app_commands.command(name="stats", description="Show property market statistics")
async def stats(interaction: discord.Interaction):
    bot = interaction.client
    try:
        logger.info(f"Stats command used by {interaction.user}")
        await interaction.response.defer()

        embed = discord.Embed(
            title="Property Market Statistics",
            color=discord.Color.blue(),
            description="Current market overview"
        )

        for property_type in bot.property_types:
            properties = bot.properties[property_type]
            if properties:
                prices = [prop['price'] for prop in properties]
                avg_price = sum(prices) / len(prices)
                min_price = min(prices)
                max_price = max(prices)
                
                display_name = property_type.replace('_', ' ').title()
                if property_type in ['office_leases', 'storage_units']:
                    price_suffix = "/month"
                else:
                    price_suffix = ""
                
                stats_text = (
                    f"Total listings: {len(properties)}\n"
                    f"Average price: ${avg_price:,.2f}{price_suffix}\n"
                    f"Lowest price: ${min_price:,}{price_suffix}\n"
                    f"Highest price: ${max_price:,}{price_suffix}"
                )
                
                embed.add_field(
                    name=display_name,
                    value=stats_text,
                    inline=False
                )
            else:
                embed.add_field(
                    name=property_type.replace('_', ' ').title(),
                    value="No listings available",
                    inline=False
                )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await interaction.followup.send("An error occurred while fetching market statistics.")

def main():
    try:
        # Validate environment variables
        validate_env_variables()
        
        # Create and run the bot
        bot = PropertyBot()
        logger.info("Starting bot...")
        bot.run(DISCORD_TOKEN)
        
    except discord.errors.LoginFailure:
        logger.error("Failed to login. Please check your Discord token.")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    main()