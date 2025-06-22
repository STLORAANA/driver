from flask import Flask, render_template, request, redirect, session, url_for, flash
app = Flask(__name__)
from datetime import datetime, date
import csv, os

from driver.user import USERS, RATE_PER_PACKAGE



app.secret_key = 'change-this-secret-key'

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def get_csv_path(username):
    return os.path.join(DATA_DIR, f"{username}.csv")


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        if USERS.get(username) == password:
            session['username'] = username
            return redirect(url_for('dashboard'))
        flash("❌ Invalid username or password.")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    is_admin = (session['username'] == 'admin')
    if is_admin:
        return render_template('admin_dashboard.html', user=session['username'])
    else:
        return render_template('dashboard.html', user=session['username'], admin=is_admin)

def process_add_entry(target_username, form_data):
    try:
        route = form_data['route']
        assigned = int(form_data['assigned'])
        delivered = int(form_data['delivered'])
        returns = int(form_data['returns'])
        missing = assigned - (delivered + returns)
        main_id = form_data['main_id']
        your_id = form_data['your_id']
        id_ranges = form_data['id_ranges']
        date_obj = datetime.strptime(form_data['date'], "%Y-%m-%d")

        if route not in RATE_PER_PACKAGE:
            flash(f"❌ Invalid route: {route}.")
            return False, "Invalid route"
        if missing < 0:
            flash("❌ Delivered + Returns exceed assigned packages.")
            return False, "Invalid package counts"

        dr, mr = RATE_PER_PACKAGE[route]
        pay, prof = dr * delivered, (mr - dr) * delivered

        csv_path = get_csv_path(target_username)
        new_file = not os.path.exists(csv_path)
        with open(csv_path, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["Date","Route","Assigned","Delivered","Returns","Missing","Profit($)","DriverPay($)","Main ID","Your ID","ID Ranges"])
            w.writerow([date_obj.strftime("%Y-%m-%d"), route, assigned, delivered, returns, missing,
                        f"{prof:.2f}", f"{pay:.2f}", main_id, your_id, id_ranges])
        return True, "Entry added successfully."
    except ValueError as e:
        flash(f"❌ Invalid input: {e}. Please ensure numbers are entered correctly.")
        return False, "Invalid input"
    except Exception as e:
        flash(f"❌ An error occurred: {e}")
        return False, "Error"


@app.route('/add', methods=['GET', 'POST'])
def add_entry():
    if 'username' not in session or session['username'] == 'admin':
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        success, message = process_add_entry(session['username'], request.form)
        if success:
            flash("✅ Entry added!")
            return redirect(url_for('dashboard'))
        else:
            flash(message)
    
    current_date = date.today().isoformat()
    return render_template("add_entry.html", current_date=current_date)


@app.route('/summary/<half>')
def summary(half):
    if 'username' not in session or session['username'] == 'admin':
        return redirect(url_for('dashboard'))
    return render_summary(session['username'], half)

def render_summary(username, half):
    csv_path = get_csv_path(username)
    if not os.path.exists(csv_path):
        flash("❌ No data found for your account.")
        return redirect(url_for('dashboard'))

    rows = []
    total_pay = 0
    route_counts = {}

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            date_obj = datetime.strptime(r["Date"], "%Y-%m-%d")
            if (half == 'first' and date_obj.day > 15) or (half == 'second' and date_obj.day <= 15):
                continue
            delivered = int(r["Delivered"])
            pay = float(r["DriverPay($)"])
            rows.append({
                "date": r["Date"],
                "route": r["Route"],
                "delivered": delivered,
                "pay": pay
            })
            total_pay += pay
            route_counts[r["Route"]] = route_counts.get(r["Route"], 0) + delivered

    if not rows:
        flash(f"❌ No entries found for the {half} half of the month.")
        return redirect(url_for('dashboard'))

    return render_template("summary.html", rows=rows, total_pay=total_pay, route_counts=route_counts, half=half)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("👋 Logged out successfully.")
    return redirect(url_for('login'))

# ------------------- ADMIN ROUTES -------------------

@app.route('/admin/add_entry', methods=['GET', 'POST'])
def admin_add_entry():
    if 'username' not in session or session['username'] != 'admin':
        flash("🚫 Access denied. Admin privileges required.")
        return redirect(url_for('dashboard'))

    non_admin_users = [u for u in USERS if u != 'admin']

    if request.method == 'POST':
        target_username = request.form['target_username'].strip().lower()
        if target_username not in USERS or target_username == 'admin':
            flash("❌ Invalid or admin user selected.")
            current_date = date.today().isoformat()
            return render_template("admin_add_entry.html", users=non_admin_users, current_date=current_date)

        success, message = process_add_entry(target_username, request.form)
        if success:
            flash(f"✅ Entry added for {target_username}!")
            return redirect(url_for('dashboard')) # Corrected: Changed 'admin_dashboard' to 'dashboard'
        else:
            flash(message)
            current_date = date.today().isoformat()
            return render_template("admin_add_entry.html", users=non_admin_users, current_date=current_date)

    current_date = date.today().isoformat()
    return render_template("admin_add_entry.html", users=non_admin_users, current_date=current_date)


@app.route('/admin/salary_report/<half>')
def admin_salary_report(half):
    if 'username' not in session or session['username'] != 'admin':
        flash("🚫 Access denied. Admin privileges required.")
        return redirect(url_for('dashboard'))

    summary_data = {}
    total_company_pay = 0
    total_company_profit = 0

    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".csv"):
            username_from_file = filename[:-4]
            if username_from_file != 'admin' and username_from_file in USERS:
                csv_path = get_csv_path(username_from_file)
                if os.path.exists(csv_path):
                    with open(csv_path, newline="") as f:
                        reader = csv.DictReader(f)
                        for r in reader:
                            try:
                                date_obj = datetime.strptime(r["Date"], "%Y-%m-%d")
                                if (half == 'first' and date_obj.day > 15) or \
                                   (half == 'second' and date_obj.day <= 15):
                                    continue

                                delivered = int(r["Delivered"])
                                driver_pay = float(r["DriverPay($)"])
                                profit = float(r["Profit($)"])

                                summary_data.setdefault(username_from_file, {"delivered": 0, "pay": 0})
                                summary_data[username_from_file]["delivered"] += delivered
                                summary_data[username_from_file]["pay"] += driver_pay
                                total_company_pay += driver_pay
                                total_company_profit += profit
                            except (ValueError, KeyError) as e:
                                print(f"Skipping row in {filename} due to data error: {e}, row: {r}")
                                continue

    if not summary_data:
        flash(f"❌ No driver data available for the {half} half of the month.")
        return redirect(url_for('dashboard'))

    to_collect_from_john = total_company_pay + total_company_profit

    return render_template('admin_salary_report.html',
                           summary=summary_data,
                           total_company_pay=total_company_pay,
                           total_company_profit=total_company_profit,
                           to_collect_from_john=to_collect_from_john,
                           half=half)

@app.route('/admin/generate_all_summary_csv')
def admin_generate_all_summary_csv():
    if 'username' not in session or session['username'] != 'admin':
        flash("🚫 Access denied. Admin privileges required.")
        return redirect(url_for('dashboard'))

    all_rows = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".csv"):
            username_from_file = filename[:-4]
            if username_from_file != 'admin' and username_from_file in USERS:
                csv_path = get_csv_path(username_from_file)
                if os.path.exists(csv_path):
                    with open(csv_path, newline="") as f:
                        reader = csv.DictReader(f)
                        for r in reader:
                            try:
                                date_str = r["Date"]
                                route = r["Route"]
                                delivered = int(r["Delivered"])
                                driver_pay = float(r["DriverPay($)"])
                                profit = float(r["Profit($)"])

                                all_rows.append([
                                    date_str,
                                    username_from_file,
                                    route,
                                    delivered,
                                    f"{driver_pay:.2f}",
                                    f"{profit:.2f}"
                                ])
                            except (ValueError, KeyError) as e:
                                print(f"Skipping row in {filename} due to data error: {e}, row: {r}")
                                continue

    if not all_rows:
        flash("❌ No driver data found to export.")
    else:
        all_rows.sort(key=lambda x: (datetime.strptime(x[0], "%Y-%m-%d"), x[1]))
        output_csv_path = os.path.join(DATA_DIR, "all_summary.csv")

        with open(output_csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Driver", "Route", "Delivered", "DriverPay($)", "Profit($)"])
            writer.writerows(all_rows)
        flash("✅ 'all_summary.csv' created and saved to the 'data' folder!")

    return redirect(url_for('dashboard')) # Corrected: Changed 'admin_dashboard' to 'dashboard'
if __name__ == '__main__':
    # You can choose any available port, for example, 8000, 8080, or 5001
    # For this example, let's use port 8000
    app.run(debug=True, host='0.0.0.0', port=8000)
