import random
import string
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


def generate_password(length=10, use_digits=True, use_lower=True, use_upper=True, use_special=True):
    """生成可配置字符集和长度的强密码"""
    pools = []
    if use_digits:
        pools.append(string.digits)
    if use_lower:
        pools.append(string.ascii_lowercase)
    if use_upper:
        pools.append(string.ascii_uppercase)
    if use_special:
        pools.append("!@#$%^&*()-_=+[]{}|;:,.<>?")

    # 至少保留一个字符池（防御性处理）
    if not pools:
        pools.append(string.digits)

    all_chars = "".join(pools)

    # 若长度足够，每类至少取一个，保证各类型必然出现
    if length >= len(pools):
        password = [random.choice(pool) for pool in pools]
        password += random.choices(all_chars, k=length - len(pools))
    else:
        password = random.choices(all_chars, k=length)

    random.shuffle(password)
    return "".join(password)


@app.route("/")
def index():
    password = generate_password()
    return render_template("index.html", password=password)


@app.route("/generate")
def generate():
    length = request.args.get("length", 10, type=int)
    length = max(1, min(50, length))
    use_digits = request.args.get("digits", "1") == "1"
    use_lower = request.args.get("lower", "1") == "1"
    use_upper = request.args.get("upper", "1") == "1"
    use_special = request.args.get("special", "1") == "1"
    password = generate_password(length, use_digits, use_lower, use_upper, use_special)
    return jsonify({"password": password})


if __name__ == "__main__":
    app.run(debug=True)
