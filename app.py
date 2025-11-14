from flask import Flask, render_template, request, flash, jsonify
import config
import mysql.connector as connector
from werkzeug.utils import secure_filename
import os
from ultralytics import YOLO
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def connect_to_db():
    try:
        connection = connector.connect(**config.mysql_credentials)
        return connection
    except connector.Error as e:
        print(f"Error connecting to database: {e}")
        return None

@app.route('/')
def dashboard():
    """
    Renders the main dashboard and populates the car brand dropdown.
    """
    brands = []
    connection = connect_to_db()
    if connection:
        try:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT DISTINCT brand FROM car_models ORDER BY brand ASC")
                brands = [row['brand'] for row in cursor.fetchall()]
        except connector.Error as e:
            print(f"Error fetching brands: {e}")
            flash("Could not load car brands from the database.", "error")
        finally:
            if connection.is_connected():
                connection.close()

    return render_template('dashboard.html', brands=brands)

@app.route('/get-models/<brand>')
def get_models(brand):
    """
    API endpoint to get car models for a specific brand.
    """
    models = []
    connection = connect_to_db()
    if connection:
        try:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT DISTINCT model FROM car_models WHERE brand = %s ORDER BY model ASC", (brand,))
                models = [row['model'] for row in cursor.fetchall()]
        except connector.Error as e:
            print(f"Error fetching models: {e}")
        finally:
            if connection.is_connected():
                connection.close()
    return jsonify(models)

# Load YOLO model
model_path = "C:\Users\shivj\Desktop\Final_Year_project\models\best.pt"
model = YOLO(model_path)

@app.route('/estimate', methods=['POST'])
def estimate():
    """
    Handles image upload, damage detection, and cost estimation.
    """
    if 'image' not in request.files:
        flash('Please upload an image.', 'error')
        return render_template('dashboard.html')

    file = request.files['image']
    car_brand = request.form.get('car_brand')
    car_model = request.form.get('car_model')

    if file.filename == '' or not car_brand or not car_model:
        flash('Please select a car brand, model, and upload an image.', 'error')
        return render_template('dashboard.html')

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        flash('Invalid file type. Please upload an image.', 'error')
        return render_template('dashboard.html')
    
    # Save the uploaded image
    image_path = os.path.join('D:/Vehicle Damage Detection/static', 'uploaded_image.jpg')
    file.save(image_path)
    
    # Make predictions using YOLO
    result = model(image_path)
    class_ids = [box.cls.item() for box in result[0].boxes]
    class_counts = Counter(class_ids)
    
    # Save the image with detections
    detected_image_path = os.path.join('D:/Vehicle Damage Detection/static', 'detected_image.jpg')
    result[0].save(filename=detected_image_path)
    
    # Fetch part prices from the database
    part_prices = get_part_prices(car_brand, car_model, class_counts)

    return render_template('estimate.html', 
                           original_image='uploaded_image.jpg', 
                           detected_image='detected_image.jpg', 
                           part_prices=part_prices)

def get_part_prices(car_brand, car_model, class_counts):
    connection = connect_to_db()
    if not connection:
        flash("Database connection failed.", "error")
        return {}
    
    prices = {}
    try:
        with connection.cursor(dictionary=True) as cursor:
            for class_id, count in class_counts.items():
                part_name = get_part_name_from_id(class_id)
                if part_name:
                    cursor.execute(
                        "SELECT price FROM car_models WHERE brand = %s AND model = %s AND part = %s",
                        (car_brand, car_model, part_name)
                    )
                    price_data = cursor.fetchone()
                    if price_data:
                        price_per_part = price_data['price']
                        total_price = price_per_part * count
                        prices[part_name] = {'count': count, 'price': price_per_part, 'total': total_price}
    except connector.Error as e:
        print(f"Error executing query: {e}")
        return {}
    finally:
        if connection.is_connected():
            connection.close()
            
    return prices

def get_part_name_from_id(class_id):
    class_names = ['Bonnet', 'Bumper', 'Dickey', 'Door', 'Fender', 'Light', 'Windshield']
    if 0 <= class_id < len(class_names):
        return class_names[int(class_id)]
    return None

if __name__ == '__main__':
    app.run(debug=True)