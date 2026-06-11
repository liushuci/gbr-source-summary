from __future__ import annotations

import pandas as pd


def rsr_rating(value):
    if pd.isna(value):
        return "Insufficient data"

    if 0 <= value <= 0.5:
        return "Very good"
    if 0.5 < value <= 0.6:
        return "Good"
    if 0.6 < value <= 0.7:
        return "Satisfactory"
    return "Unsatisfactory"


def pbias_rating(value, constituent):
    if pd.isna(value):
        return "Insufficient data"

    v = abs(value)

    if constituent == "Flow":
        if v < 5:
            return "Very good"
        if v < 10:
            return "Good"
        if v < 15:
            return "Satisfactory"
        return "Unsatisfactory"

    if constituent == "FS":
        if v < 10:
            return "Very good"
        if v < 15:
            return "Good"
        if v < 20:
            return "Satisfactory"
        return "Unsatisfactory"

    if constituent in ["TN", "PN", "DIN", "DON", "TP", "PP", "DIP", "DOP"]:
        if v < 15:
            return "Very good"
        if v < 20:
            return "Good"
        if v < 30:
            return "Satisfactory"
        return "Unsatisfactory"

    return "Insufficient data"


def nse_rating(value, constituent):
    if pd.isna(value):
        return "Insufficient data"

    if constituent == "Flow":
        if value > 0.8:
            return "Very good"
        if value > 0.7:
            return "Good"
        if value > 0.5:
            return "Satisfactory"
        return "Unsatisfactory"

    if constituent == "FS":
        if value > 0.8:
            return "Very good"
        if value > 0.7:
            return "Good"
        if value > 0.45:
            return "Satisfactory"
        return "Unsatisfactory"

    if constituent in ["TN", "PN", "DIN", "DON", "TP", "PP", "DIP", "DOP"]:
        if value > 0.65:
            return "Very good"
        if value > 0.5:
            return "Good"
        if value > 0.35:
            return "Satisfactory"
        return "Unsatisfactory"

    return "Insufficient data"


def r2_rating(value, constituent):
    if pd.isna(value):
        return "Insufficient data"

    if constituent == "Flow":
        if value > 0.85:
            return "Very good"
        if value > 0.75:
            return "Good"
        if value > 0.60:
            return "Satisfactory"
        return "Unsatisfactory"

    if constituent == "FS":
        if value > 0.8:
            return "Very good"
        if value > 0.65:
            return "Good"
        if value > 0.4:
            return "Satisfactory"
        return "Unsatisfactory"

    if constituent in ["TN", "PN", "DIN", "DON"]:
        if value > 0.7:
            return "Very good"
        if value > 0.6:
            return "Good"
        if value > 0.3:
            return "Satisfactory"
        return "Unsatisfactory"

    if constituent in ["TP", "PP", "DIP", "DOP"]:
        if value > 0.8:
            return "Very good"
        if value > 0.65:
            return "Good"
        if value > 0.4:
            return "Satisfactory"
        return "Unsatisfactory"

    return "Insufficient data"