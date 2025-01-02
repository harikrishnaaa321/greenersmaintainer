from flask import Flask, request, render_template, redirect, url_for, flash, session
import pymongo
from bson import ObjectId
from dotenv import load_dotenv
import os
import re
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from datetime import datetime
load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

mongo_uri = os.getenv("MONGO_URI")
client = pymongo.MongoClient(mongo_uri)
db = client.greeners
users_collection = db['users']

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_sales = db.sales.find({"user_id": ObjectId(session['user_id'])})

    total_sales = 0
    total_crops_sold = 0
    pending_sales = 0

    for sale in user_sales:
        quantity = float(sale.get('quantity', 0))
        price = float(sale.get('amount_paid', 0))
        total_sales += price
        total_crops_sold += quantity

        if sale.get('status') == 'pending':
            pending_sales += 1

    return render_template(
        'home.html', 
        total_sales=total_sales, 
        total_crops_sold=total_crops_sold,
        pending_sales=pending_sales
    )


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        return redirect(url_for('home', username=user['username']))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        phone_number = request.form['phone_number']
        email = request.form['email']

        if not validate_email(email):
            flash("Invalid email format.", "error")
            return render_template('signup.html')

        if not validate_phone_number(phone_number):
            flash("Invalid phone number format. It should be a 10-digit number.", "error")
            return render_template('signup.html')

        if users_collection.find_one({"username": username}):
            flash("Username already exists. Please choose another.", "error")
            return render_template('signup.html')

        if users_collection.find_one({"email": email}):
            flash("Email already exists. Please use another.", "error")
            return render_template('signup.html')

        hashed_password = generate_password_hash(password)

        user = {
            "username": username,
            "password": hashed_password,
            "phone_number": phone_number,
            "email": email
        }
        users_collection.insert_one(user)
        flash("User registered successfully!", "success")
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/login', methods=['POST', 'GET'])
def login():
    if 'user_id' in session:
        user = users_collection.find_one({"_id": ObjectId(session['user_id'])})
        return redirect(url_for('home', username=user['username']))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_collection.find_one({"email": email})
        
        if user and check_password_hash(user['password'], password):
            flash("Login successful!", "success")
            session.permanent = True
            session['user_id'] = str(user['_id'])
            return redirect(url_for('home'))
        else:
            flash("Invalid credentials. Please try again.", "error")
            return render_template('login.html')

    return render_template('login.html')

@app.route('/add_record', methods=['GET', 'POST'])
def add_record():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        buyer_name = request.form['buyer_name']
        crop_name = request.form['crop_name']
        quantity = request.form['quantity']
        price_per_kg = request.form['price_per_kg']
        amount_paid = request.form['amount_paid']

        if not buyer_name or not crop_name or not quantity or not price_per_kg or not amount_paid:
            flash("All fields are required.", "error")
            return render_template('add_record.html')

        try:
            quantity = float(quantity)
            price_per_kg = float(price_per_kg)
            amount_paid = float(amount_paid)
        except ValueError:
            flash("Please enter valid numeric values for quantity, price per kg, and amount paid.", "error")
            return render_template('add_record.html')

        total_bill = quantity * price_per_kg
        if amount_paid > total_bill:
            flash("Amount paid cannot exceed total bill.", "error")
            return render_template('add_record.html')

        status = 'pending' if amount_paid < total_bill else 'completed'
        date = datetime.now()

        record = {
            'user_id': ObjectId(session['user_id']),
            'buyer_name': buyer_name,
            'crop_name': crop_name,
            'quantity': quantity,
            'price_per_kg': price_per_kg,
            'total_bill': total_bill,
            'amount_paid': amount_paid,
            'status': status,
            'date': date
        }

        db.sales.insert_one(record)
        flash("Record added successfully!", "success")
        return redirect(url_for('home'))

    return render_template('add_record.html')

@app.route('/track_sales')
def track_sales():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_sales = db.sales.find({"user_id": ObjectId(session['user_id'])})

    sales_records = list(user_sales)

    return render_template('track_sales.html', sales_records=sales_records)

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})

    if user:
        user_sales = db.sales.find({"user_id": ObjectId(session['user_id'])})
        total_sales = 0
        total_crops_sold = 0

        for sale in user_sales:
            total_sales += float(sale['quantity']) * float(sale['price_per_kg'])
            total_crops_sold += float(sale['quantity'])

        total_profit_loss = total_sales  

        return render_template('profile.html', 
                               username=user['username'], 
                               email=user['email'], 
                               phone_number=user['phone_number'], 
                               total_profit_loss=total_profit_loss)
    
    flash("User not found.", "error")
    return redirect(url_for('login'))

@app.route('/update_password', methods=['GET', 'POST'])
def update_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = users_collection.find_one({"_id": ObjectId(session['user_id'])})

    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if not check_password_hash(user['password'], current_password):
            flash("Current password is incorrect.", "error")
            return render_template('update_password.html')

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('update_password.html')

        hashed_password = generate_password_hash(new_password)
        users_collection.update_one({"_id": ObjectId(session['user_id'])}, {"$set": {"password": hashed_password}})
        flash("Password updated successfully!", "success")
        return redirect(url_for('profile'))

    return render_template('update_password.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

def validate_email(email):
    email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(email_regex, email) is not None

def validate_phone_number(phone):
    phone_regex = r'^\d{10}$'
    return re.match(phone_regex, phone) is not None

if __name__ == '__main__':
    app.run(debug=True)
