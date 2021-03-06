from flask import Flask, render_template, request,redirect,url_for, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import date
from flask_wtf.csrf import CSRFProtect
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, DateTimeField, TextAreaField
from wtforms.validators import Email, Length, InputRequired
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from Util.Gmail_API import send_email
from Util.Security import ts
from Settings.App_Settings import SECRETKEY, TRACKMODIFICATIONS
from Settings.DB_Settings import dbuser,dbpass,dbhost,dbname
from APIs import Wikipedia
from APIs.movies import movies
from APIs.spoiler import Spoiler
from flask_apscheduler import APScheduler
from itertools import count
import time

'''
Setup the app with all of its environment
'''
#region AppSetup
app = Flask(__name__)

app.config['SECRET_KEY'] = SECRETKEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://{0}:{1}@{2}/{3}'.format(dbuser,dbpass,dbhost,dbname)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = TRACKMODIFICATIONS
app.config['SQLALCHEMY_POOL_RECYCLE'] = 600 - 1

db = SQLAlchemy()
db.init_app(app)

csrf = CSRFProtect()
csrf.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

SPOILER = Spoiler()

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()
#endregion


'''
Setup Classes Needed
'''
#region Classes
class User(db.Model,UserMixin):
    __tablename__ = 'Users'
    id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    full_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(50), nullable=False,unique=True)
    password_hash = db.Column(db.String(300), nullable=False)
    phone_number = db.Column(db.String(50), nullable=False)
    date_joined = db.Column(db.String(50), nullable=False)
    number_interactions = db.Column(db.Integer, nullable=False)

    def __init__(self, email, password_hash, name, date, phone_number, number_interactions):
        self.email = email
        self.full_name = name
        self.date_joined = date
        self.password_hash = password_hash
        self.phone_number = phone_number
        self.number_interactions = number_interactions

    def __repr__(self):
        return '<User %r>' % self.full_name

class SentSpoiler(db.Model,UserMixin):
    __tablename__ = 'SentSpoilers'
    id = db.Column(db.Integer, primary_key=True,autoincrement=True)
    from_user = db.Column(db.String(30), nullable=False)
    to_email = db.Column(db.String(30), nullable=False,unique=True)
    spoiler = db.Column(db.String(), nullable=False)
    date_sent = db.Column(db.String(50), nullable=False)

    def __init__(self, from_user, to_email, spoiler):
        self.from_user = from_user
        self.to_email = to_email
        self.spoiler = spoiler
        self.date_sent = date.today()

    def __repr__(self):
        return '<from: {0} , to:{1} , date: {2}>'.format(self.from_user, self.to_email, self.date_sent)




#endregion



'''
Setup Forms
'''
#region Forms
class RegistrationForm(FlaskForm):   
    email = StringField('email',  validators=[InputRequired(), Email(message='Invalid email'), Length(max=30)])
    name = StringField('name',  validators=[InputRequired(), Length(max=30)])
    password = PasswordField('password', validators=[InputRequired(), Length(min=0, max=20)])

class LoginForm(FlaskForm):
    email = StringField('email',  validators=[InputRequired(), Email(message='Invalid email'), Length(max=30)])
    password = PasswordField('password', validators=[InputRequired(), Length(min=8, max=20)])

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[InputRequired(), Email(message='Invalid email'), Length(max=30)])

class ResetPasswordForm(FlaskForm):
    password = PasswordField('password', validators=[InputRequired(), Length(min=8, max=20)])

class PickAMovieForm(FlaskForm):
    movie_name = StringField('movie_name',  validators=[InputRequired(), Length(max=30)])

class BuildASpoiler(FlaskForm):
    movie_name = StringField('movie_name',  validators=[InputRequired(), Length(max=30)])
    victim_email = StringField('Email', validators=[InputRequired(), Email(message='Invalid email'), Length(max=30)])
    spoiler = TextAreaField('spoiler',  validators=[InputRequired()], id="spoiler")

class ContactUsForm(FlaskForm):
    from_name = StringField('from_name',  validators=[InputRequired(), Length(max=30)])
    message = StringField('message',  validators=[InputRequired(), Length(max=30)])
#endregion

'''
User Management Authentication 
'''
#region User Managment

@login_manager.user_loader
def load_user(user_id):
    return User.query.filter_by(id=user_id).first()
    
@app.route("/signup",methods=['GET','POST'])
def register_user():
    form = RegistrationForm()

    if request.method == 'GET':
        return render_template('user_management/signup.html', form=form)

    elif request.method == 'POST':
        if form.validate_on_submit():
            existing_email = User.query.filter_by(email=form.email.data).first()
            if existing_email is not None:
                return render_template('user_management/signup.html', form=form, error="Email taken")  # We should return a pop up error msg as well account taken
            else:
                hashpass = generate_password_hash(form.password.data, method='sha256')
                newUser = User(name=form.name.data, email=form.email.data,password_hash=hashpass,number_interactions=1,date=date.today(),phone_number="")
                db.session.add(newUser)
                db.session.commit()
                session['email'] = form.email.data
                login_user(newUser)
                return redirect(url_for('pick_movie',justsignedup=True))
        return render_template('user_management/signup.html', form=form, loggedin = current_user.is_authenticated) #We should return a pop up error msg as well bad input


@app.route("/login", methods=['GET', 'POST'])
def Login():
    form = LoginForm()

    if request.method == 'GET':
        error_message = request.args.get('error_message')
        if current_user.is_authenticated == True:
            return redirect(url_for('pick_movie'))
        return render_template('user_management/login.html', form=form, loggedin = current_user.is_authenticated, error=error_message)

    elif request.method == 'POST':
        check_user = User.query.filter_by(email=form.email.data).first()
        if check_user:
            if check_password_hash(check_user.password_hash, form.password.data):
                login_user(check_user)
                session['email'] = form.email.data
                return redirect(url_for('pick_movie'))
            return render_template('user_management/login.html', form=form, error="Incorrect password!", loggedin = current_user.is_authenticated)
        else:
            return render_template('user_management/login.html', form=form, error="Email doesn't exist!", loggedin = current_user.is_authenticated)

@app.route('/logout', methods = ['GET'])
@login_required
def logout():
    logout_user()
    try:
        del session['access_token']
    except Exception:
        pass
    return redirect(url_for('Login'))

@app.route('/resetpassword', methods=["GET", "POST"])
def reset():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first_or_404()
        subject = "Password reset requested"
        token = ts.dumps(user.email, salt='recover-key')
        recover_url = url_for(
            'reset_with_token',
            token=token,
            _external=True)
        html = render_template(
            'email/recover_password.html',
            recover_url=recover_url)

        send_email(user.email, subject, html)

        return redirect(url_for('landing_page'))

    return render_template('user_management/forgot_password.html', form=form)

@app.route('/resetpassword/<token>', methods=["GET", "POST"])
def reset_with_token(token):
    try:
        email = ts.loads(token, salt="recover-key", max_age=86400)
    except:
        abort(404)

    form = ResetPasswordForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=email).first_or_404()
        user.password_hash = generate_password_hash(form.password.data, method='sha256')
        db.session.add(user)
        db.session.commit()

        return redirect(url_for('Login'))

    return render_template('user_management/reset_password.html', form=form, token=token)

#endregion 


#region spoiler
@app.route("/getmovieinfo",methods=['GET'])     # Used for Autocomplete
def getmovieinfo():
    if(current_user.is_authenticated):
        movie = request.args.get('term')
        movieC = movies()
        suggestions = movieC.getmoviesuggestions(movie)
        return jsonify(suggestions) 
    else:
        return redirect(url_for('Login',error_message = "Interesting seeing you here, login to view stuff"))



@app.route("/pick-a-movie",methods=['GET','POST'])   
def pick_movie():
    if(current_user.is_authenticated):
        form = PickAMovieForm()
        if request.method == 'GET':  
            return render_template('spoilers/pick_a_movie.html', form = form, loggedin = current_user.is_authenticated)
    else:
        return redirect(url_for('Login',error_message = "Login to pick a movie and start building a spoiler"))

@app.route("/build-spoiler",methods=['GET','POST'])
def build_spoiler():
    if(current_user.is_authenticated):
        dat = request.form
        try:
            name = dat.to_dict()['movie_name']
            if(name):
                spoiler = SPOILER.GenerateWikipediaSpoiler(name)
        except Exception:
            spoiler = None
        form = BuildASpoiler(spoiler=spoiler)
        return render_template('spoilers/build_a_spoiler.html', form = form, loggedin = current_user.is_authenticated, spoiler = spoiler)
    else:
        return redirect(url_for('Login',error_message = "Login to build a spoiler (We don't want people spamming their friends anonymously)"))


counter = lambda c=count(): next(c)
@app.route("/scheduler-spoiler",methods=['GET','POST'])
def scheduler_spoiler():
    if(current_user.is_authenticated):
        try:
            dat = request.form.to_dict()
            form = BuildASpoiler()
            newSpoiler = SentSpoiler(from_user = session['email'], to_email = dat['victim_email'].strip(), spoiler = dat['spoiler'])
            db.session.add(newSpoiler)
            db.session.commit()
            app.apscheduler.add_job(func=schedule_email, trigger='date', args=[dat['victim_email'],dat['spoiler']], id='j' + str(counter))
            return redirect(url_for('landing_page',message = "Congrats your spoiler was sent to : " + dat['victim_email']))
        except Exception:
            return redirect(url_for('landing_page',message = "Whoops something went wrong, this is still a work in progress so sorry about that"))
    else:
        return redirect(url_for('Login',error_message = "Login to schedule a spoiler (We don't want people spamming their friends anonymously)"))

def schedule_email(email,spoiler):
    send_email(email, "This is not a spoiler", spoiler)

@app.route("/spoiler-history")
def spoiler_history():
    if(current_user.is_authenticated):
        data = SentSpoiler.query.filter_by(from_user=session['email']).all()
        return render_template('spoilers/history.html', loggedin = current_user.is_authenticated, data = list(data))
    else:
        return redirect(url_for('Login',error_message = "Login to view your sent spoiler history"))

#endregion




@app.route("/")
def landing_page():
    message = request.args.get('message')
    return render_template('landing_page.html', loggedin = current_user.is_authenticated, justsignedup = request.args.get('justsignedup'),message=message)

@app.route("/about-us")
def about_us():
    return render_template('about_us.html', loggedin = current_user.is_authenticated)


@app.route("/contact",methods=['GET','POST'])
def user_settings():
    form = ContactUsForm()
    if(current_user.is_authenticated):
        if request.method == "GET":
            return render_template('user_management/contact.html', loggedin = current_user.is_authenticated, form=form)
        else:
            send_email("yahia@yahiabakour.com", "CONTACT FORM FILLED BY : " + form.from_name.data, "MESSAGE : " + form.message.data)
            return render_template('user_management/contact.html', loggedin = current_user.is_authenticated, form=form, message="Thank you for contacting us, we'll be intouch shortly")
    else:
        return redirect(url_for('Login',error_message = "Login first !"))




#region error handling
@app.errorhandler(404)
def page_error(e):
    return render_template('error/404.html', loggedin = current_user.is_authenticated), 404

@app.errorhandler(500)
def exception_error():
    return render_template('error/500.html', loggedin = current_user.is_authenticated), 500

#endregion

if __name__ == '__main__':
    app.run(debug=True)
