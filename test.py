
from db import get_connection


def main():
    connection = None

    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            cursor.execute("SELECT 'Oracle connected!' FROM dual")
            result = cursor.fetchone()

            print(result[0])

    except Exception as error:
        print("Database connection failed.")
        print(error)

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
