"""Synthetic account records. Names deliberately span scripts, diacritics and transliterations."""

ACCOUNTS = [
    {"account_id": "acct_1001", "platform": "ecommerce", "legal_name": "Acme Widgets LLC",
     "aliases": ["Acme Widget Store"], "address": "1200 Market Street, San Francisco, CA 94102"},
    {"account_id": "acct_1002", "platform": "ads", "legal_name": "Nguyễn Văn An Trading Company",
     "aliases": [], "address": "45 Bolsa Avenue, Westminster, CA 92683"},
    {"account_id": "acct_1003", "platform": "live", "legal_name": "Zhang Wei Imports Inc",
     "aliases": ["ZW Imports"], "address": "88 Canal Street, New York, NY 10013"},
    {"account_id": "acct_1004", "platform": "payments", "legal_name": "Muhammad Al-Rashid Foods LLC",
     "aliases": [], "address": "300 Main Street, Dearborn, MI 48126"},
    {"account_id": "acct_1005", "platform": "ecommerce", "legal_name": "José García Construcción LLC",
     "aliases": ["Garcia Construction"], "address": "910 Elm Street, Houston, TX 77002"},
    {"account_id": "acct_1006", "platform": "ads", "legal_name": "Ōkubo Design Studio Ltd",
     "aliases": [], "address": "17 Grant Avenue, San Francisco, CA 94108"},
    {"account_id": "acct_1007", "platform": "live", "legal_name": "Oluwaseun Adeyemi Media Inc",
     "aliases": ["Seun Media"], "address": "2200 Peachtree Road, Atlanta, GA 30309"},
    {"account_id": "acct_1008", "platform": "payments", "legal_name": "Kowalczyk & Sons Plumbing Inc",
     "aliases": [], "address": "55 Milwaukee Avenue, Chicago, IL 60622"},
    {"account_id": "acct_1009", "platform": "ecommerce", "legal_name": "Priya Raghunathan Consulting LLC",
     "aliases": [], "address": "1 Technology Drive, Edison, NJ 08837"},
    {"account_id": "acct_1010", "platform": "ads", "legal_name": "Søren Østergaard Bikes Inc",
     "aliases": [], "address": "700 Pearl Street, Boulder, CO 80302"},
    {"account_id": "acct_1011", "platform": "live", "legal_name": "Aleksandr Volkov Logistics LLC",
     "aliases": [], "address": "12 Ocean Parkway, Brooklyn, NY 11218"},
    {"account_id": "acct_1012", "platform": "payments", "legal_name": "Lê Thị Hồng Nail Salon LLC",
     "aliases": ["Hong Nails"], "address": "8 Westminster Mall, Westminster, CA 92683"},
]

# Name origin groups for the evaluation's demographic breakdown.
NAME_GROUP = {
    "acct_1001": "anglo", "acct_1002": "vietnamese", "acct_1003": "chinese", "acct_1004": "arabic",
    "acct_1005": "hispanic", "acct_1006": "japanese", "acct_1007": "nigerian", "acct_1008": "polish",
    "acct_1009": "indian", "acct_1010": "nordic", "acct_1011": "russian", "acct_1012": "vietnamese",
}
