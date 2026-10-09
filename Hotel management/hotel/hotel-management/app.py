from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Database initialization
def init_db():
    conn = sqlite3.connect('hotel.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS rooms
                 (id INTEGER PRIMARY KEY, number TEXT, type TEXT, price REAL, status TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (id INTEGER PRIMARY KEY, guest_name TEXT, guest_email TEXT, 
                  room_id INTEGER, check_in DATE, check_out DATE, status TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admin
                 (id INTEGER PRIMARY KEY, username TEXT, password TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bills
                 (id INTEGER PRIMARY KEY, 
                  booking_id INTEGER,
                  room_charge REAL,
                  tax_amount REAL,
                  total_amount REAL,
                  payment_status TEXT DEFAULT 'Pending',
                  created_date DATE,
                  FOREIGN KEY (booking_id) REFERENCES bookings (id))''')
    
    # Insert sample data if not exists
    c.execute("SELECT COUNT(*) FROM rooms")
    if c.fetchone()[0] == 0:
        # Insert sample rooms
        rooms = [
            ('101', 'Single', 100.00, 'Available'),
            ('102', 'Single', 100.00, 'Available'),
            ('201', 'Double', 150.00, 'Available'),
            ('202', 'Double', 150.00, 'Available'),
            ('301', 'Suite', 250.00, 'Available'),
            ('302', 'Suite', 250.00, 'Available')
        ]
        c.executemany("INSERT INTO rooms (number, type, price, status) VALUES (?, ?, ?, ?)", rooms)
        
        # Insert admin credentials
        c.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ('admin', 'admin123'))
    
    conn.commit()
    conn.close()

# Database connection helper
def get_db_connection():
    conn = sqlite3.connect('hotel.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/book', methods=['POST'])
def book_room():
    if request.method == 'POST':
        guest_name = request.form['guest_name']
        guest_email = request.form['guest_email']
        room_type = request.form['room_type']
        check_in = request.form['check_in']
        check_out = request.form['check_out']
        
        conn = get_db_connection()
        
        # Find available room of requested type
        room = conn.execute(
            'SELECT * FROM rooms WHERE type = ? AND status = "Available" LIMIT 1',
            (room_type,)
        ).fetchone()
        
        if room:
            # Book the room
            conn.execute(
                'INSERT INTO bookings (guest_name, guest_email, room_id, check_in, check_out, status) VALUES (?, ?, ?, ?, ?, ?)',
                (guest_name, guest_email, room['id'], check_in, check_out, 'Confirmed')
            )
            
            # Update room status
            conn.execute(
                'UPDATE rooms SET status = "Booked" WHERE id = ?',
                (room['id'],)
            )
            
            conn.commit()
            conn.close()
            
            flash('Room booked successfully!', 'success')
        else:
            conn.close()
            flash('No available rooms of the selected type.', 'error')
        
        return redirect(url_for('index'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        admin = conn.execute(
            'SELECT * FROM admin WHERE username = ? AND password = ?',
            (username, password)
        ).fetchone()
        conn.close()
        
        if admin:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials. Please try again.', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    
    # Get all rooms
    rooms = conn.execute('SELECT * FROM rooms').fetchall()
    
    # Get all bookings
    bookings = conn.execute('''
        SELECT bookings.*, rooms.number as room_number, rooms.type as room_type 
        FROM bookings 
        JOIN rooms ON bookings.room_id = rooms.id
        ORDER BY bookings.check_in DESC
    ''').fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', rooms=rooms, bookings=bookings)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/update_room_status', methods=['POST'])
def update_room_status():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    room_id = request.form['room_id']
    new_status = request.form['status']
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE rooms SET status = ? WHERE id = ?',
        (new_status, room_id)
    )
    conn.commit()
    conn.close()
    
    flash('Room status updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_booking_status', methods=['POST'])
def update_booking_status():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    booking_id = request.form['booking_id']
    new_status = request.form['status']
    
    conn = get_db_connection()
    
    # If changing to Cancelled, free up the room
    if new_status == 'Cancelled':
        booking = conn.execute('SELECT * FROM bookings WHERE id = ?', (booking_id,)).fetchone()
        if booking:
            conn.execute(
                'UPDATE rooms SET status = "Available" WHERE id = ?',
                (booking['room_id'],)
            )
    
    conn.execute(
        'UPDATE bookings SET status = ? WHERE id = ?',
        (new_status, booking_id)
    )
    conn.commit()
    conn.close()
    
    flash('Booking status updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/generate_bill/<int:booking_id>')
def generate_bill(booking_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    
    # Get booking details
    booking = conn.execute('''
        SELECT bookings.*, rooms.number, rooms.type, rooms.price
        FROM bookings 
        JOIN rooms ON bookings.room_id = rooms.id 
        WHERE bookings.id = ?
    ''', (booking_id,)).fetchone()
    
    if not booking:
        flash('Booking not found.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Calculate number of days
    check_in = datetime.strptime(booking['check_in'], '%Y-%m-%d')
    check_out = datetime.strptime(booking['check_out'], '%Y-%m-%d')
    num_days = (check_out - check_in).days
    
    # Calculate charges
    room_charge = booking['price'] * num_days
    tax_rate = 0.10  # 10% tax
    tax_amount = room_charge * tax_rate
    total_amount = room_charge + tax_amount
    
    # Check if bill already exists
    existing_bill = conn.execute(
        'SELECT * FROM bills WHERE booking_id = ?', (booking_id,)
    ).fetchone()
    
    if not existing_bill:
        # Create new bill
        conn.execute('''
            INSERT INTO bills (booking_id, room_charge, tax_amount, total_amount, created_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (booking_id, room_charge, tax_amount, total_amount, datetime.now().date()))
        conn.commit()
        flash('Bill generated successfully!', 'success')
    else:
        flash('Bill already exists for this booking.', 'info')
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/view_bills')
def view_bills():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    
    bills = conn.execute('''
        SELECT bills.*, bookings.guest_name, bookings.guest_email, 
               rooms.number as room_number, rooms.type as room_type,
               bookings.check_in, bookings.check_out
        FROM bills
        JOIN bookings ON bills.booking_id = bookings.id
        JOIN rooms ON bookings.room_id = rooms.id
        ORDER BY bills.created_date DESC
    ''').fetchall()
    
    conn.close()
    return render_template('view_bills.html', bills=bills)

@app.route('/admin/update_payment_status', methods=['POST'])
def update_payment_status():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    bill_id = request.form['bill_id']
    payment_status = request.form['payment_status']
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE bills SET payment_status = ? WHERE id = ?',
        (payment_status, bill_id)
    )
    conn.commit()
    conn.close()
    
    flash('Payment status updated successfully!', 'success')
    return redirect(url_for('view_bills'))

@app.route('/admin/print_invoice/<int:bill_id>')
def print_invoice(bill_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    
    bill = conn.execute('''
        SELECT bills.*, bookings.guest_name, bookings.guest_email, 
               rooms.number as room_number, rooms.type as room_type, rooms.price as room_price,
               bookings.check_in, bookings.check_out
        FROM bills
        JOIN bookings ON bills.booking_id = bookings.id
        JOIN rooms ON bookings.room_id = rooms.id
        WHERE bills.id = ?
    ''', (bill_id,)).fetchone()
    
    conn.close()
    
    if not bill:
        flash('Bill not found.', 'error')
        return redirect(url_for('view_bills'))
    
    # Calculate number of days
    check_in = datetime.strptime(bill['check_in'], '%Y-%m-%d')
    check_out = datetime.strptime(bill['check_out'], '%Y-%m-%d')
    num_days = (check_out - check_in).days
    
    return render_template('invoice.html', bill=bill, num_days=num_days)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)