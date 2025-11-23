import os
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Инициализация приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here_change_in_production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///slots_game.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация БД и login manager
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/game.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Создание папки для логов
os.makedirs('logs', exist_ok=True)


# Модели БД
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    balance = db.Column(db.Float, default=1000.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class GameLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bet_amount = db.Column(db.Float, nullable=False)
    win_amount = db.Column(db.Float, nullable=False)
    result = db.Column(db.String(50))  # 'win', 'loss', 'jackpot'
    symbols = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('game_logs', lazy=True))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Маршруты авторизации
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # Валидация
        if not username or not email or not password:
            logger.warning(f'Попытка регистрации с неполными данными: {username}')
            return render_template('register.html', error='Заполните все поля'), 400

        if password != confirm_password:
            logger.warning(f'Попытка регистрации с несовпадающими паролями: {username}')
            return render_template('register.html', error='Пароли не совпадают'), 400

        if User.query.filter_by(username=username).first():
            logger.warning(f'Попытка регистрации с существующим username: {username}')
            return render_template('register.html', error='Пользователь с таким именем уже существует'), 400

        if User.query.filter_by(email=email).first():
            logger.warning(f'Попытка регистрации с существующим email: {email}')
            return render_template('register.html', error='Email уже зарегистрирован'), 400

        # Создание нового пользователя
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        logger.info(f'Новый пользователь зарегистрирован: {username}')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            logger.info(f'Пользователь вошел: {username}')
            return redirect(url_for('index'))
        else:
            logger.warning(f'Неудачная попытка входа: {username}')
            return render_template('login.html', error='Неверное имя пользователя или пароль'), 401

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    logger.info(f'Пользователь вышел: {username}')
    return redirect(url_for('login'))


# Игровые маршруты
@app.route('/')
@login_required
def index():
    logger.info(f'Пользователь {current_user.username} посетил главную страницу')
    return render_template('index.html', user=current_user)


@app.route('/spin', methods=['POST'])
@login_required
def spin():
    import random

    data = request.json
    bet_amount = float(data.get('bet', 0))

    # Валидация ставки
    if bet_amount <= 0 or bet_amount > current_user.balance:
        logger.warning(f'Пользователь {current_user.username} попытался поставить некорректную сумму: {bet_amount}')
        return jsonify({'error': 'Некорректная ставка'}), 400

    symbols = ['🍎', '🍊', '🍋', '🍌', '🍓']
    spin_result = [random.choice(symbols) for _ in range(3)]

    # Проверка выигрыша
    win_amount = 0
    result_type = 'loss'

    if spin_result[0] == spin_result[1] == spin_result[2]:
        win_amount = bet_amount * 100
        result_type = 'jackpot'
        logger.info(f'ДЖЕКПОТ! Пользователь {current_user.username} выиграл {win_amount}. Символы: {spin_result}')
    elif spin_result[0] == spin_result[1] or spin_result[1] == spin_result[2]:
        win_amount = bet_amount * 10
        result_type = 'win'
        logger.info(f'Выигрыш! Пользователь {current_user.username} выиграл {win_amount}. Символы: {spin_result}')
    else:
        logger.info(f'Проигрыш. Пользователь {current_user.username} потерял {bet_amount}. Символы: {spin_result}')

    # Обновление баланса
    current_user.balance = current_user.balance - bet_amount + win_amount

    # Логирование игры в БД
    game_log = GameLog(
        user_id=current_user.id,
        bet_amount=bet_amount,
        win_amount=win_amount,
        result=result_type,
        symbols=', '.join(spin_result)
    )
    db.session.add(game_log)
    db.session.commit()

    return jsonify({
        'symbols': spin_result,
        'win': win_amount,
        'new_balance': current_user.balance,
        'result': result_type
    })


@app.route('/balance')
@login_required
def get_balance():
    return jsonify({'balance': current_user.balance})


@app.route('/history')
@login_required
def history():
    logs = GameLog.query.filter_by(user_id=current_user.id).order_by(GameLog.created_at.desc()).limit(50).all()
    logger.info(f'Пользователь {current_user.username} просмотрел историю игр')
    return render_template('history.html', logs=logs, user=current_user)


@app.errorhandler(404)
def not_found(error):
    logger.warning(f'Ошибка 404: страница не найдена')
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f'Ошибка 500: {error}')
    return render_template('500.html'), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    logger.info('Приложение запущено')
