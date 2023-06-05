#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from flask import (
    Flask, Blueprint, flash, g, redirect, render_template, request, session, url_for, jsonify, Response
)
import json

# create and configure the app
app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html")


@app.route("/instances", methods=["GET", "POST"])
def instances():
    return render_template("instances.html")


@app.route("/hashtag", methods=["GET", "POST"])
def hashtag():
    return render_template("index.html")


@app.route("/public", methods=["GET", "POST"])
def public():
    return render_template("index.html")


@app.route("/sample", methods=["GET", "POST"])
def sample():
    return render_template("index.html")


@app.route("/interactions", methods=["GET", "POST"])
def interactions():
    return render_template("index.html")


@app.route("/export", methods=["GET", "POST"])
def export():
    return render_template("index.html")


if __name__ == "__main__":
    app.run()
