# Creating a global logger for the application
# logger/__init__.py
from .custom_logger import CustomLogger
# Create a single shared logeer instance and where ever we have to use the logger instance we ca nuse the global logger varibale
GLOBAL_LOGGER = CustomLogger().get_logger("prod_assistant")