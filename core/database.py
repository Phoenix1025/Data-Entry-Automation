# core/database.py

import sqlite3
import logging
import re
from typing import Optional, Dict, Any
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DatabaseManager:
    # ... (Keep __init__, __enter__, __exit__, connect, close, sanitize_name, create_dynamic_table as they were in the last complete version) ...
    def __init__(self, db_path: str = 'data/database.db'):
        self.db_path = Path(db_path).resolve()
        self.connection: Optional[sqlite3.Connection] = None
        logging.info(f"DatabaseManager initialized for path: {self.db_path}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self) -> bool:
        if self.connection: return True
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            logging.info(f"Successfully connected to database: {self.db_path} (SQLite v{sqlite3.sqlite_version})")
            return True
        except sqlite3.Error as e:
            logging.error(f"Database connection error to {self.db_path}: {e}", exc_info=True)
            self.connection = None
            return False
        except OSError as e:
             logging.error(f"OS error preventing database connection (check permissions or path): {self.db_path}: {e}", exc_info=True)
             self.connection = None
             return False

    def close(self):
        if self.connection:
            try:
                # Attempt to commit any lingering transaction before closing, then rollback if commit fails
                try:
                     if self.connection.in_transaction:
                           logging.info("Attempting final commit before closing.")
                           self.connection.commit()
                except sqlite3.Error as commit_err:
                     logging.warning(f"Final commit failed before close (rolling back): {commit_err}")
                     try:
                           self.connection.rollback()
                     except Exception as rb_err:
                           logging.error(f"Rollback during close failed: {rb_err}")

                self.connection.close()
                logging.info(f"Database connection closed: {self.db_path}")
            except sqlite3.Error as e:
                logging.error(f"Error closing database connection {self.db_path}: {e}", exc_info=True)
            finally:
                 self.connection = None
        else:
            logging.debug("Attempted to close an already closed or non-existent database connection.")


    def execute(self, query: str, params: tuple = (), commit: bool = False) -> Optional[sqlite3.Cursor]:
        """Execute a SQL query with improved transaction handling."""
        if not self.connection:
            logging.error("Database execute error: Not connected.")
            return None

        cursor = None
        try:
            # Start transaction explicitly? Not typically needed for single statements with commit=True,
            # but might help in complex scenarios. Let's try rollback first.
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            if commit:
                self.connection.commit()
                # logging.info(f"Committed transaction for query: {query[:50]}...") # Optional success log
            return cursor
        except sqlite3.Error as e:
            logging.error(f"Database execution error: {e}\nQuery: {query}\nParams: {params}", exc_info=True)
            # --- Attempt Rollback on Error ---
            # Check if connection exists and seems usable before rollback
            if self.connection:
                try:
                    logging.warning("Attempting transaction rollback due to caught database error.")
                    self.connection.rollback()
                    logging.info("Transaction rollback completed.")
                except Exception as rb_err:
                    # Log if rollback itself fails, but don't mask original error
                    logging.error(f"Rollback attempt failed: {rb_err}", exc_info=True)
            else:
                 logging.error("Cannot rollback, connection is invalid.")
            # --- End Rollback Attempt ---
            return None # Indicate failure

    def sanitize_name(self, name):
        """Sanitizes a string to be a valid SQL table/column name."""
        if not isinstance(name, str): name = str(name)
        name = re.sub(r'[^\w_]', '_', name) # Allow letters, numbers, underscore
        if name and name[0].isdigit(): name = "_" + name # Prepend underscore if starts with digit
        if not name: return None # Return None if empty after sanitization
        return name.lower() # Convert to lowercase

    def create_dynamic_table(self, table_name: str, schema_definition: Dict[str, str]) -> bool:
        """Creates a table dynamically based on the provided schema."""
        logging.info(f"create_dynamic_table received call with table_name='{table_name}'")
        sanitized_table_name = self.sanitize_name(table_name)
        logging.info(f"Sanitized table name for creation: '{sanitized_table_name}'")

        if not sanitized_table_name:
            logging.error("Table creation failed: Invalid or empty table name provided after sanitization.")
            return False
        if not schema_definition:
            logging.error(f"Table creation failed for '{sanitized_table_name}': No columns defined in schema_definition.")
            return False

        column_defs = []
        defined_sanitized_cols = {self.sanitize_name(k) for k in schema_definition.keys()}
        if 'id' not in defined_sanitized_cols:
             column_defs.append('"id" INTEGER PRIMARY KEY AUTOINCREMENT')
             logging.info(f"Automatically adding 'id INTEGER PRIMARY KEY AUTOINCREMENT' to table '{sanitized_table_name}'.")

        for col_name, col_type in schema_definition.items():
            sanitized_col_name = self.sanitize_name(col_name)
            if not sanitized_col_name:
                logging.warning(f"Skipping invalid column name '{col_name}' during table creation for '{sanitized_table_name}'.")
                continue
            validated_type = re.sub(r'[^\w\s\(\)_]', '', col_type).strip()
            if not validated_type:
                logging.warning(f"Column type for '{sanitized_col_name}' was empty or invalid ('{col_type}'), defaulting to TEXT.")
                validated_type = "TEXT"
            column_defs.append(f'"{sanitized_col_name}" {validated_type}')

        if not column_defs:
             logging.error(f"Table creation failed for '{sanitized_table_name}': No valid columns could be defined.")
             return False

        sql = f'CREATE TABLE IF NOT EXISTS "{sanitized_table_name}" ({", ".join(column_defs)});'
        logging.info(f"Attempting to execute schema statement for table '{sanitized_table_name}':\nSQL: {sql}")
        cursor = self.execute(sql, commit=True) # Execute the CREATE TABLE command

        if cursor is not None:
            logging.info(f"Table '{sanitized_table_name}' created or verified successfully.")
            return True
        else:
            logging.error(f"Failed to execute schema statement for table '{sanitized_table_name}'. Check previous error log for details.")
            return False

    def create_contacts_table(self):
        """Creates the standard 'contacts' table if it doesn't exist."""
        pass # Keep implementation if needed, removed for brevity
