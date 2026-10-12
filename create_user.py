
from getpass import getpass

from werkzeug.security import generate_password_hash
from db import get_connection


def main():
    username = input("Enter staff username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    password = getpass("Enter staff password: ")
    confirm = getpass("Confirm password: ")

    if len(password) < 8:
        print("Password must contain at least 8 characters.")
        return

    if password != confirm:
        print("Passwords do not match.")
        return

    password_hash = generate_password_hash(password)
    connection = None

    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (
                    user_id, username, password_hash, role
                )
                VALUES (
                    users_seq.NEXTVAL, :username, :password_hash, :role
                )
                """,
                {
                    "username": username,
                    "password_hash": password_hash,
                    "role": "ADMIN",
                },
            )

        connection.commit()
        print("Staff account created successfully.")

    except Exception as error:
        if connection:
            connection.rollback()

        print("Could not create the account.")
        print(error)

    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()
