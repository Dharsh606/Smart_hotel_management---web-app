from flask import Flask, render_template, request, redirect, session, flash, url_for
import sqlite3
from datetime import datetime, date
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = "hotel_secret_key_2024_secure"

# Database file path
DATABASE = "hotel.db"


def get_db():
    """Get database connection"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        # Test connection
        conn.execute("SELECT 1")
        return conn
    except sqlite3.DatabaseError:
        # Database is corrupted, recreate it
        if os.path.exists(DATABASE):
            os.remove(DATABASE)
        init_db()
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn


def init_db():
    """Initialize database with required tables"""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Test if database is valid by trying to query
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        cursor.fetchall()
    except (sqlite3.DatabaseError, sqlite3.OperationalError):
        # Database is corrupted, delete and recreate
        if conn:
            try:
                conn.close()
            except:
                pass
        if os.path.exists(DATABASE):
            try:
                os.remove(DATABASE)
            except:
                pass
        conn = get_db()
        cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Rooms table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'Available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Bookings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_name TEXT NOT NULL,
            room_id INTEGER NOT NULL,
            check_in DATE NOT NULL,
            check_out DATE NOT NULL,
            status TEXT DEFAULT 'Booked',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    """)
    
    # Activity logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            details TEXT,
            user TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create default admin user if not exists
    try:
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                ("admin", "admin123")
            )
            # Log activity after tables are created
            cursor.execute("""
                INSERT INTO activity_logs (action, details, user) 
                VALUES (?, ?, ?)
            """, ("System", "Default admin user created", "System"))
    except sqlite3.OperationalError:
        pass  # Table might not exist yet, will be created on next run
    
    # Create sample rooms if database is empty
    try:
        cursor.execute("SELECT COUNT(*) FROM rooms")
        if cursor.fetchone()[0] == 0:
            sample_rooms = [
                ("101", "Available"),
                ("102", "Available"),
                ("103", "Available"),
                ("201", "Available"),
                ("202", "Available"),
                ("301", "Available"),
                ("302", "Available"),
                ("401", "Available"),
            ]
            for room_num, status in sample_rooms:
                cursor.execute(
                    "INSERT INTO rooms (room_number, status) VALUES (?, ?)",
                    (room_num, status)
                )
            # Log activity after tables are created
            cursor.execute("""
                INSERT INTO activity_logs (action, details, user) 
                VALUES (?, ?, ?)
            """, ("System", "Sample rooms initialized", "System"))
    except sqlite3.OperationalError:
        pass  # Table might not exist yet, will be created on next run
    
    conn.commit()
    conn.close()


def log_activity(user, action, details=""):
    """Log activity to database"""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO activity_logs (action, details, user) VALUES (?, ?, ?)",
            (action, details, user)
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        # Table might not exist yet, skip logging
        pass


def login_required(f):
    """Decorator to protect routes requiring authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/", methods=["GET", "POST"])
def login():
    """Handle user login"""
    if "user" in session:
        return redirect(url_for("dashboard"))
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        if not username or not password:
            flash("Please enter both username and password", "error")
            return render_template("login.html")
        
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password)
        ).fetchone()
        conn.close()
        
        if user:
            session["user"] = username
            log_activity(username, "Login", f"User {username} logged in")
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password", "error")
    
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    """Handle user logout"""
    username = session.get("user", "Unknown")
    session.clear()
    log_activity(username, "Logout", f"User {username} logged out")
    flash("You have been logged out", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Admin dashboard with statistics"""
    conn = get_db()
    
    # Get room statistics
    total_rooms = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    available_rooms = conn.execute(
        "SELECT COUNT(*) FROM rooms WHERE status = 'Available'"
    ).fetchone()[0]
    booked_rooms = conn.execute(
        "SELECT COUNT(*) FROM rooms WHERE status = 'Booked'"
    ).fetchone()[0]
    occupied_rooms = conn.execute(
        "SELECT COUNT(*) FROM rooms WHERE status = 'Occupied'"
    ).fetchone()[0]
    
    # Get active bookings
    today = date.today().isoformat()
    active_bookings = conn.execute("""
        SELECT b.*, r.room_number 
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        WHERE b.status IN ('Booked', 'Checked In')
        ORDER BY b.check_in ASC
    """).fetchall()
    
    # Get all rooms with their current booking status
    rooms = conn.execute("""
        SELECT r.*, 
               b.guest_name, 
               b.check_in, 
               b.check_out,
               b.status as booking_status
        FROM rooms r
        LEFT JOIN bookings b ON r.id = b.room_id 
            AND b.status IN ('Booked', 'Checked In')
            AND date('now') BETWEEN b.check_in AND b.check_out
        ORDER BY r.room_number
    """).fetchall()
    
    # Get recent activity logs
    recent_logs = conn.execute("""
        SELECT * FROM activity_logs 
        ORDER BY timestamp DESC 
        LIMIT 10
    """).fetchall()
    
    conn.close()
    
    return render_template(
        "dashboard.html",
        total_rooms=total_rooms,
        available_rooms=available_rooms,
        booked_rooms=booked_rooms,
        occupied_rooms=occupied_rooms,
        active_bookings=active_bookings,
        rooms=rooms,
        recent_logs=recent_logs
    )


@app.route("/rooms")
@login_required
def rooms():
    """Display all rooms"""
    conn = get_db()
    rooms = conn.execute("""
        SELECT r.*, 
               b.guest_name, 
               b.check_in, 
               b.check_out,
               b.status as booking_status
        FROM rooms r
        LEFT JOIN bookings b ON r.id = b.room_id 
            AND b.status IN ('Booked', 'Checked In')
            AND date('now') BETWEEN b.check_in AND b.check_out
        ORDER BY r.room_number
    """).fetchall()
    conn.close()
    return render_template("rooms.html", rooms=rooms)


@app.route("/book", methods=["GET", "POST"])
@login_required
def book():
    """Handle room booking"""
    try:
        conn = get_db()
    except Exception as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect(url_for("dashboard"))
    
    if request.method == "POST":
        guest_name = request.form.get("guest_name", "").strip()
        room_id = request.form.get("room_id")
        check_in = request.form.get("check_in")
        check_out = request.form.get("check_out")
        
        # Validation
        if not all([guest_name, room_id, check_in, check_out]):
            flash("Please fill in all fields", "error")
            rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
            if rooms is None:
                rooms = []
            has_available = any(room["status"] == "Available" for room in rooms)
            today = date.today().isoformat()
            conn.close()
            return render_template("booking.html", rooms=rooms, today=today, has_available=has_available)
        
        # Check if dates are valid
        try:
            check_in_date = datetime.strptime(check_in, "%Y-%m-%d").date()
            check_out_date = datetime.strptime(check_out, "%Y-%m-%d").date()
            today = date.today()
            
            if check_in_date < today:
                flash("Check-in date cannot be in the past", "error")
                rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
                if rooms is None:
                    rooms = []
                has_available = any(room["status"] == "Available" for room in rooms)
                today = date.today().isoformat()
                conn.close()
                return render_template("booking.html", rooms=rooms, today=today, has_available=has_available)
            
            if check_out_date <= check_in_date:
                flash("Check-out date must be after check-in date", "error")
                rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
                if rooms is None:
                    rooms = []
                has_available = any(room["status"] == "Available" for room in rooms)
                today = date.today().isoformat()
                conn.close()
                return render_template("booking.html", rooms=rooms, today=today, has_available=has_available)
        except ValueError:
            flash("Invalid date format", "error")
            rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
            if rooms is None:
                rooms = []
            has_available = any(room["status"] == "Available" for room in rooms)
            today = date.today().isoformat()
            conn.close()
            return render_template("booking.html", rooms=rooms, today=today, has_available=has_available)
        
        # Check for booking conflicts
        conflict = conn.execute("""
            SELECT * FROM bookings 
            WHERE room_id = ? 
            AND status IN ('Booked', 'Checked In')
            AND (
                (check_in <= ? AND check_out >= ?) OR
                (check_in <= ? AND check_out >= ?) OR
                (check_in >= ? AND check_out <= ?)
            )
        """, (room_id, check_in, check_in, check_out, check_out, check_in, check_out)).fetchone()
        
        if conflict:
            room = conn.execute("SELECT room_number FROM rooms WHERE id = ?", (room_id,)).fetchone()
            flash(f"Room {room['room_number']} is already booked for the selected dates", "error")
            rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
            if rooms is None:
                rooms = []
            has_available = any(room["status"] == "Available" for room in rooms)
            today = date.today().isoformat()
            conn.close()
            return render_template("booking.html", rooms=rooms, today=today, has_available=has_available)
        
        # Check if room is available
        room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        if room["status"] not in ["Available"]:
            flash(f"Room {room['room_number']} is not available", "error")
            rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
            if rooms is None:
                rooms = []
            has_available = any(room["status"] == "Available" for room in rooms)
            today = date.today().isoformat()
            conn.close()
            return render_template("booking.html", rooms=rooms, today=today, has_available=has_available)
        
        # Create booking
        conn.execute("""
            INSERT INTO bookings (guest_name, room_id, check_in, check_out, status)
            VALUES (?, ?, ?, ?, ?)
        """, (guest_name, room_id, check_in, check_out, "Booked"))
        
        # Update room status
        conn.execute("UPDATE rooms SET status = 'Booked' WHERE id = ?", (room_id,))
        
        conn.commit()
        username = session.get("user", "Unknown")
        log_activity(username, "Booking Created", 
                    f"Room {room['room_number']} booked for {guest_name} ({check_in} to {check_out})")
        conn.close()
        
        flash(f"Room {room['room_number']} booked successfully for {guest_name}!", "success")
        return redirect(url_for("dashboard"))
    
    # GET request - show booking form
    try:
        # Ensure rooms table exists
        table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rooms'").fetchone()
        if not table_check:
            # Tables don't exist, initialize database
            conn.close()
            init_db()
            conn = get_db()
        
        rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
        # Ensure rooms is always a list
        if rooms is None:
            rooms = []
        
        # Check if any rooms are available
        has_available = any(room["status"] == "Available" for room in rooms)
        
        conn.close()
        today = date.today().isoformat()
        return render_template("booking.html", rooms=rooms or [], today=today, has_available=has_available)
    except sqlite3.OperationalError as e:
        # Database error - try to reinitialize
        try:
            conn.close()
        except:
            pass
        try:
            init_db()
            conn = get_db()
            rooms = conn.execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
            if rooms is None:
                rooms = []
            has_available = any(room["status"] == "Available" for room in rooms)
            conn.close()
            today = date.today().isoformat()
            return render_template("booking.html", rooms=rooms, today=today, has_available=has_available)
        except Exception as e2:
            flash(f"Database error: {str(e2)}. Please restart the application.", "error")
            return redirect(url_for("dashboard"))
    except Exception as e:
        try:
            conn.close()
        except:
            pass
        flash(f"Error loading rooms: {str(e)}. Please try again.", "error")
        return redirect(url_for("dashboard"))


@app.route("/checkin/<int:booking_id>")
@login_required
def checkin(booking_id):
    """Handle check-in"""
    conn = get_db()
    
    booking = conn.execute("""
        SELECT b.*, r.room_number 
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        WHERE b.id = ?
    """, (booking_id,)).fetchone()
    
    if not booking:
        flash("Booking not found", "error")
        conn.close()
        return redirect(url_for("dashboard"))
    
    if booking["status"] != "Booked":
        flash("This booking cannot be checked in", "error")
        conn.close()
        return redirect(url_for("dashboard"))
    
    # Update booking status
    conn.execute("UPDATE bookings SET status = 'Checked In' WHERE id = ?", (booking_id,))
    
    # Update room status
    conn.execute("UPDATE rooms SET status = 'Occupied' WHERE id = ?", (booking["room_id"],))
    
    conn.commit()
    username = session.get("user", "Unknown")
    log_activity(username, "Check-In", 
                f"Room {booking['room_number']} checked in for {booking['guest_name']}")
    conn.close()
    
    flash(f"Check-in successful for Room {booking['room_number']}!", "success")
    return redirect(url_for("dashboard"))


@app.route("/checkout/<int:booking_id>")
@login_required
def checkout(booking_id):
    """Handle check-out"""
    conn = get_db()
    
    booking = conn.execute("""
        SELECT b.*, r.room_number 
        FROM bookings b
        JOIN rooms r ON b.room_id = r.id
        WHERE b.id = ?
    """, (booking_id,)).fetchone()
    
    if not booking:
        flash("Booking not found", "error")
        conn.close()
        return redirect(url_for("dashboard"))
    
    if booking["status"] not in ["Booked", "Checked In"]:
        flash("This booking cannot be checked out", "error")
        conn.close()
        return redirect(url_for("dashboard"))
    
    # Update booking status
    conn.execute("UPDATE bookings SET status = 'Completed' WHERE id = ?", (booking_id,))
    
    # Update room status to Available
    conn.execute("UPDATE rooms SET status = 'Available' WHERE id = ?", (booking["room_id"],))
    
    conn.commit()
    username = session.get("user", "Unknown")
    log_activity(username, "Check-Out", 
                f"Room {booking['room_number']} checked out for {booking['guest_name']}")
    conn.close()
    
    flash(f"Check-out successful for Room {booking['room_number']}!", "success")
    return redirect(url_for("dashboard"))


@app.route("/logs")
@login_required
def logs():
    """Display activity logs"""
    conn = get_db()
    all_logs = conn.execute("""
        SELECT * FROM activity_logs 
        ORDER BY timestamp DESC 
        LIMIT 100
    """).fetchall()
    conn.close()
    return render_template("logs.html", logs=all_logs)


if __name__ == "__main__":
    # Initialize database - handles both new and existing databases
    # Will recreate if corrupted
    init_db()
    
    app.run(debug=True, host="0.0.0.0", port=5000)
