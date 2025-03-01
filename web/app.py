from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from bson import ObjectId
from datetime import datetime
import os
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import secrets
from pymongo import MongoClient
import openpyxl
from math import radians, sin, cos, sqrt, atan2
from flask_restful import Api, Resource
from werkzeug.security import generate_password_hash, check_password_hash


# Initialize Flask app
app = Flask(__name__)
app.secret_key = secrets.token_hex(24)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize MongoDB Client
app.config["MONGO_URI"] = "mongodb+srv://rakantaher:vxnP77zA4HWgB7l7@cluster0.u4h50.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(app.config["MONGO_URI"])
mongo = client.get_database('mydatabase')  # Use your actual database name here
db = client["maintenance_db"]  # ✅ Define the database before using it
sites_collection = db["sites"]
# Check MongoDB connection
try:
    mongo.command('ping')
    print("Connected to MongoDB successfully!")
except Exception as e:
    print(f"Error: {e}")
    mongo_db = None  # Set to None if there's an issue

# Haversine formula for distance calculation
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # Radius of the Earth in kilometers
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return distance

# Check if within geo range
def check_if_within_geo_range(lat1, lon1, lat2, lon2, radius_km=1.0):
    distance = haversine(lat1, lon1, lat2, lon2)
    return distance <= radius_km

@app.route('/')
def index():
    return render_template('index.html')



# Flask-RESTful API for report
api = Api(app)
class ReportAPI(Resource):
    def get(self, report_id):
        report = mongo.db.reports.find_one({"_id": ObjectId(report_id)})
        if report:
            return jsonify(report)
        return {'message': 'Report not found'}, 404

api.add_resource(ReportAPI, '/api/report/<report_id>')

# User class for Flask-Login integration
class User(UserMixin):
    def __init__(self, id, username, email, role=None):
        self.id = id
        self.username = username
        self.email = email
        self.role = role

    def get_id(self):
        return str(self.id)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_superuser(self):
        return self.role == 'superuser'

    @property
    def is_supervisor(self):
        return self.role == 'supervisor'

    @property
    def is_technician(self):
        return self.role == 'technician'



@app.route('/superuser/dashboard')
@login_required
def superuser_dashboard():
    if not current_user.is_superuser:  # If not a superuser, redirect to a general dashboard
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))  # Redirect to regular dashboard

    # Superuser-specific actions can go here, such as managing other users
    return render_template('superuser_dashboard.html')


@app.route('/manage_locations')
def manage_locations():
    # Get the sites data from the database
    sites = mongo.db.sites.find()

    # Pass the sites data to the template
    return render_template('manage_locations.html', sites=sites)


@app.route('/admin_users', methods=['GET', 'POST'])
def admin_users():
    if request.method == 'POST':
        # Get the data from the form
        user_type = request.form['user_type']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Hash the password before saving to the database
        hashed_password = generate_password_hash(password)

        # Add the user to the MongoDB database
        new_user = {
            'username': username,
            'email': email,
            'user_type': user_type,
            'password': hashed_password
        }
        mongo.db.users.insert_one(new_user)  # Insert new user

        # Redirect to the same page to display the updated list of users
        return redirect(url_for('admin_users'))

    # If it's a GET request, display the list of users
    users = mongo.db.users.find()  # Get all users from the database
    return render_template('admin_users.html', users=users)


@app.route('/edit_user/<user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    user = mongo.db.users.find_one_or_404({'_id': ObjectId(user_id)})

    if request.method == 'POST':
        # Update user fields
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']

        # Hash the new password before updating
        hashed_password = generate_password_hash(password)

        # Update user in MongoDB
        mongo.db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'username': username, 'email': email, 'user_type': user_type, 'password': hashed_password}}
        )

        return redirect(url_for('admin_users'))

    return render_template('edit_user.html', user=user)


@app.route('/delete_user/<user_id>', methods=['POST'])
def delete_user(user_id):
    # Delete user from MongoDB
    mongo.db.users.delete_one({'_id': ObjectId(user_id)})
    return redirect(url_for('admin_users'))



@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(id=user_data['_id'], username=user_data['username'], email=user_data['email'], role=user_data['role'])
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user_data = mongo.db.users.find_one({'username': username})

        if user_data and check_password_hash(user_data['password'], password):  # Verifying password hash
            user = User(id=user_data['_id'], username=user_data['username'], email=user_data['email'],
                        role=user_data['role'])
            login_user(user)

            # Redirect to specific dashboards based on user role
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))  # Admin dashboard
            elif user.is_superuser:
                return redirect(url_for('superuser_dashboard'))  # Superuser dashboard
            elif user.is_supervisor:
                return redirect(url_for('supervisor_dashboard'))  # Supervisor dashboard
            elif user.is_technician:
                return redirect(url_for('technician_dashboard'))  # Technician dashboard
            else:
                return redirect(url_for('dashboard'))  # Default user dashboard

        flash('Invalid credentials', 'danger')  # If login fails, show error
    return render_template('login.html')


# Define the route for technician dashboard
@app.route('/technician_dashboard')
@login_required
def technician_dashboard():
    if not current_user.is_technician:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    # Fetch assigned tasks for the technician from MongoDB (using MongoDB for task details)
    assigned_tasks = mongo.db.tasks.find({'technician_id': current_user.id})

    # Fetch site details for each task (from MongoDB)
    for task in assigned_tasks:
        site = mongo.db.sites.find_one({'_id': task['site_id']})
        task['site'] = site  # Add site details to the task

    # Count tasks by status using MongoDB
    completed_tasks_count = mongo.db.tasks.count_documents({'technician_id': current_user.id, 'status': 'Completed'})
    in_progress_tasks_count = mongo.db.tasks.count_documents({'technician_id': current_user.id, 'status': 'In Progress'})
    pending_tasks_count = mongo.db.tasks.count_documents({'technician_id': current_user.id, 'status': 'Pending'})

    # Render the technician dashboard template with the required data
    return render_template(
        'technician_dashboard.html',
        assigned_tasks=assigned_tasks,
        completed_tasks_count=completed_tasks_count,
        in_progress_tasks_count=in_progress_tasks_count,
        pending_tasks_count=pending_tasks_count
    )



@app.route('/submit_visit_report', methods=['POST'])
@login_required
def submit_visit_report():
    if request.method == 'POST':
        task_id = request.form['task_id']
        issue_type = request.form['issue_type']
        description = request.form['description']
        priority = request.form['priority']

        # Fetch the task from the MongoDB database
        task = mongo.db.tasks.find_one({'_id': task_id})

        if task:
            # Update the task fields
            task['issue_type'] = issue_type
            task['description'] = description
            task['priority'] = priority
            task['status'] = 'In Progress'  # or 'Resolved' based on further conditions

            # Commit the changes to the database
            mongo.db.tasks.update_one({'_id': task_id}, {'$set': task})

            flash('Visit report submitted successfully.', 'success')
        else:
            flash('Task not found.', 'danger')

        return redirect(url_for('technician_dashboard'))


@app.route('/technician/task/<task_id>', methods=['GET', 'POST'])
@login_required
def view_task(task_id):
    if not current_user.is_technician:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        # Ensure task_id is converted to ObjectId before querying
        task = mongo.db.tasks.find_one({'_id': ObjectId(task_id)})
        if not task:
            flash("Task not found.", "danger")
            return redirect(url_for('technician_dashboard'))
    except Exception as e:
        flash(f"Invalid ID format: {e}", "danger")
        return redirect(url_for('technician_dashboard'))

    # Pass the task to the template
    return render_template('view_task.html', task=task)


@app.route('/dashboard')
@login_required
def dashboard():
    return f'Hello, {current_user.id}'

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin_dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:  # Check if user is admin
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    # 1. Convert today's date to a datetime object (with time set to midnight)
    today = datetime.today()
    start_of_day = datetime.combine(today, datetime.min.time())  # Midnight of today
    end_of_day = datetime.combine(today, datetime.max.time())  # End of day (11:59:59 PM)

    # 2. Fetch total visits for today (updated query with datetime)
    total_visits = mongo.db.visits.count_documents({'visit_date': {'$gte': start_of_day, '$lte': end_of_day}})

    # 3. Fetch planned sites for today (adjust query according to your collection structure)
    planned_sites = mongo.db.sites.find({'visit_date': {'$gte': start_of_day, '$lte': end_of_day}})

    # 4. Fetch issue statistics (example aggregation to count issues)
    issue_stats = mongo.db.tasks.aggregate([
        {"$group": {"_id": "$issue_type", "count": {"$sum": 1}}}
    ])

    # 5. Fetch site statistics (example aggregation)
    site_stats = mongo.db.sites.aggregate([
        {"$group": {"_id": "$location", "site_count": {"$sum": 1}}}
    ])

    # Render the dashboard template with the fetched data
    return render_template(
        'admin_dashboard.html',
        total_visits=total_visits,
        planned_sites=planned_sites,
        issue_stats=issue_stats,
        site_stats=site_stats
    )

def get_site_data():
    # Fetch data from the 'sites' collection in MongoDB
    total_sites = mongo.db.sites.count_documents({})
    active_sites = mongo.db.sites.count_documents({'status': 'Active'})
    closed_sites = mongo.db.sites.count_documents({'status': 'Closed'})

    return {
        'total_sites': total_sites,
        'active_sites': active_sites,
        'closed_sites': closed_sites
    }

def get_issue_stats():
    # Perform an aggregation to get counts of each type of issue
    issue_stats = mongo.db.tasks.aggregate([
        { "$group": {
            "_id": "$issue_type",  # Group by issue type
            "count": { "$sum": 1 }  # Count occurrences
        }}
    ])
    return list(issue_stats)  # Return as a list for easier rendering


from functools import wraps
from flask import redirect, url_for, flash

def superuser_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_superuser:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard'))  # Redirect to dashboard
        return f(*args, **kwargs)
    return decorated_function

@app.route('/superuser/only-access-page')
@superuser_required
def only_for_superusers():
    # Code for page accessible only to superusers
    return render_template('superuser_page.html')


# Supervisor report submission route
@app.route('/supervisor/submit_report', methods=['POST'])
@login_required
def submit_report():
    lat = float(request.form.get('latitude'))
    lon = float(request.form.get('longitude'))
    site_id = request.form.get('site_id')

    site = mongo.db.sites.find_one({'_id': ObjectId(site_id)})

    if not check_if_within_geo_range(lat, lon, site['geo_coordinates']['lat'], site['geo_coordinates']['long']):
        flash("You are outside the allowed site location.", "danger")
        return redirect(url_for('dashboard'))

    issue_type = request.form.get('issue_type')
    issue_description = request.form.get('issue_description')
    solution_taken = request.form.get('solution_taken')
    priority = request.form.get('priority')

    mongo.db.reports.insert_one({
        'user_id': current_user.id,
        'site_id': site_id,
        'visit_date': datetime.utcnow(),
        'issue_type': issue_type,
        'issue_description': issue_description,
        'solution_taken': solution_taken,
        'priority': priority
    })

    flash("Report submitted successfully!", "success")
    return redirect(url_for('dashboard'))

# Export reports to Excel
@app.route('/admin/export_excel', methods=['GET', 'POST'])
def export_excel():
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    reports = mongo.db.reports.find({
        'visit_date': {'$gte': start_date, '$lte': end_date}
    })
    df = pd.DataFrame(list(reports))
    file_path = "reports.xlsx"
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)


@app.route('/supervisor/plan_visits', methods=['GET', 'POST'])
@login_required
def plan_visits():
    if not current_user.is_supervisor:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        # Supervisor plans visits for a month
        site_id = request.form['site_id']
        visit_date = request.form['visit_date']
        mongo.db.visits.insert_one({
            'site_id': site_id,
            'visit_date': visit_date,
            'supervisor_id': current_user.id
        })
        flash('Visit planned successfully!', 'success')
        return redirect(url_for('plan_visits'))

    # Fetch visits for the supervisor's dashboard
    visits = mongo.db.visits.find({'supervisor_id': current_user.id})
    return render_template('plan_visits.html', visits=visits)

@app.route('/supervisor/dashboard')
@login_required
def supervisor_dashboard():
    # Fetch assigned tasks or reports for the supervisor
    tasks = mongo.db.tasks.find({'supervisor_id': current_user.id})
    return render_template('supervisor_dashboard.html', tasks=tasks)


@app.route('/add_site', methods=['GET', 'POST'])
@login_required
def add_site():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        location = request.form.get('location')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        supervisor_id = request.form.get('supervisor_id')

        # Validate required fields
        if not name or not location or not latitude or not longitude or not supervisor_id:
            return "All fields are required!", 400

        # ✅ Insert into MongoDB
        site_data = {
            "name": name,
            "location": location,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "supervisor_id": supervisor_id,
            "status": "Active"
        }
        sites_collection.insert_one(site_data)  # Now `db` and `sites_collection` are defined

        return redirect(url_for('add_site'))  # Redirect after submission

    return render_template('add_site.html')


@app.route('/add_supervisor')
@login_required
def add_supervisor():
    return render_template('add_supervisor.html')



@app.route('/admin_sites')
@login_required
def admin_sites():
    sites = list(sites_collection.find())  # Fetch all sites from MongoDB
    return render_template('admin_sites.html', sites=sites)


@app.route('/delete_site/<site_id>', methods=['POST'])
@login_required
def delete_site(site_id):
    try:
        sites_collection.delete_one({"_id": ObjectId(site_id)})
        flash("تم حذف الموقع بنجاح!", "success")
    except Exception as e:
        flash(f"حدث خطأ: {str(e)}", "danger")

    return redirect(url_for('admin_sites'))


@app.route('/assign_sites_to_supervisor', methods=['POST'])
def assign_sites_to_supervisor():
    supervisor_id = request.form['supervisor']
    site_id = request.form['site']

    mongo.db.sites.update_one(
        {"_id": site_id},
        {"$set": {"supervisor_id": supervisor_id}}  # Update supervisor_id for the site
    )
    return redirect(url_for('admin_dashboard'))


@app.route('/add_problem_type', methods=['POST'])
def add_problem_type():
    problem_name = request.form['problem_name']

    new_problem = {
        "name": problem_name
    }

    mongo.db.problem_types.insert_one(new_problem)  # Insert new problem type into MongoDB
    return redirect(url_for('admin_dashboard'))


@app.route('/add_solution', methods=['POST'])
def add_solution():
    solution_name = request.form['solution_name']

    new_solution = {
        "name": solution_name
    }

    mongo.db.solutions.insert_one(new_solution)  # Insert new solution into MongoDB
    return redirect(url_for('admin_dashboard'))


@app.route('/admin_supervisors')
@login_required
def admin_supervisors():
    return render_template('admin_supervisors.html')

@app.route('/assign_supervisor')
@login_required
def assign_supervisor():
    return render_template('assign_supervisor.html')

@app.route('/edit_site')
@login_required
def edit_site():
    return render_template('edit_site.html')

@app.route('/edit_supervisor')
@login_required
def edit_supervisor():
    return render_template('edit_supervisor.html')

@app.route('/log_visit')
@login_required
def log_visit():
    return render_template('log_visit.html')


@app.route('/admin/sites', methods=['GET', 'POST'])
@login_required
def manage_sites():
    if not (current_user.is_admin or current_user.is_superuser):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        # Add new site data
        site_name = request.form['site_name']
        latitude = float(request.form['latitude'])
        longitude = float(request.form['longitude'])
        radius = float(request.form['radius'])
        supervisor_id = request.form['supervisor_id']

        mongo.db.sites.insert_one({
            'site_name': site_name,
            'geo_coordinates': {'lat': latitude, 'long': longitude},
            'radius': radius,
            'supervisor_id': supervisor_id
        })

        flash('Site added successfully!', 'success')
        return redirect(url_for('manage_sites'))

    # Fetch sites to display in the admin dashboard
    sites = mongo.db.sites.find()
    return render_template('admin_sites.html', sites=sites)


@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')



@app.route('/supervisor_visits')
@login_required
def supervisor_visits():
    return render_template('supervisor_visits.html')


@app.route('/supervisor/visit_report/<site_id>', methods=['GET', 'POST'])
@login_required
def visit_report(site_id):
    if not current_user.is_supervisor:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    site = mongo.db.sites.find_one({'_id': ObjectId(site_id)})

    if request.method == 'POST':
        issue_type = request.form['issue_type']
        issue_description = request.form['issue_description']
        solution_taken = request.form['solution_taken']
        priority = request.form['priority']

        # Check if within geo-range
        lat = float(request.form['latitude'])
        lon = float(request.form['longitude'])
        if not check_if_within_geo_range(lat, lon, site['geo_coordinates']['lat'], site['geo_coordinates']['long']):
            flash('You are outside the allowed site location.', 'danger')
            return redirect(url_for('visit_report', site_id=site_id))

        # Insert the report into MongoDB
        mongo.db.reports.insert_one({
            'user_id': current_user.id,
            'site_id': site_id,
            'visit_date': datetime.utcnow(),
            'issue_type': issue_type,
            'issue_description': issue_description,
            'solution_taken': solution_taken,
            'priority': priority
        })
        flash("Report submitted successfully!", "success")
        return redirect(url_for('supervisor_dashboard'))

    return render_template('visit_report.html', site=site)



@app.route('/admin/statistics')
@login_required
def statistics():
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    # Aggregating statistics data
    visit_stats = mongo.db.reports.aggregate([
        {"$group": {"_id": "$issue_type", "count": {"$sum": 1}}}
    ])

    # Processing data for chart rendering
    stats_labels = [stat['_id'] for stat in visit_stats]
    stats_counts = [stat['count'] for stat in visit_stats]

    return render_template(
        'statistics.html',
        stats_labels=stats_labels,
        stats_counts=stats_counts
    )



# Run the app
if __name__ == "__main__":
    app.run(debug=True)
