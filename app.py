
import ipaddress
import re
import socket
import time
from datetime import datetime

import pandas as pd
import streamlit as st


# -------------------- PAGE CONFIG --------------------
st.set_page_config(
    page_title="DNS Resolution Simulator",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(145deg, #0b1220 0%, #101b2d 100%);
    }
    [data-testid="stSidebar"] {
        background: #0b1322;
        border-right: 1px solid #26364c;
    }
    .hero {
        padding: 25px 28px;
        border: 1px solid #29445b;
        border-radius: 18px;
        background: linear-gradient(120deg, #132b40, #123b45);
        margin-bottom: 22px;
    }
    .hero h1 {
        font-size: 2.15rem;
        margin: 0;
        color: #f1f7ff;
    }
    .hero p {
        color: #b7cadb;
        margin-top: 8px;
        margin-bottom: 0;
    }
    .step-card {
        background: #132238;
        border: 1px solid #2b405a;
        border-radius: 12px;
        padding: 15px;
        min-height: 125px;
    }
    .step-card h4 {
        color: #5eead4;
        margin: 0 0 8px 0;
        font-size: 1rem;
    }
    .step-card p {
        color: #d6e1ee;
        font-size: 0.9rem;
        margin: 0;
    }
    div[data-testid="stMetric"] {
        background: #122136;
        border: 1px solid #263c54;
        border-radius: 12px;
        padding: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------- DEMO DNS DATABASE --------------------
# These are illustrative records for simulation, not live DNS data.
DEMO_DNS = {
    "example.com": {
        "A": ["203.0.113.10"],
        "AAAA": ["2001:db8::10"],
        "TTL": 300,
    },
    "google.com": {
        "A": ["203.0.113.20", "203.0.113.21"],
        "AAAA": ["2001:db8::20"],
        "TTL": 180,
    },
    "github.com": {
        "A": ["203.0.113.30"],
        "AAAA": ["2001:db8::30"],
        "TTL": 240,
    },
    "openai.com": {
        "A": ["203.0.113.40"],
        "AAAA": ["2001:db8::40"],
        "TTL": 180,
    },
    "wikipedia.org": {
        "A": ["203.0.113.50"],
        "AAAA": ["2001:db8::50"],
        "TTL": 300,
    },
}


# -------------------- HELPERS --------------------
def normalize_domain(value):
    """Normalize and validate a domain name."""
    domain = value.strip().lower().rstrip(".")

    if not domain:
        raise ValueError("Please enter a domain name.")

    if len(domain) > 253:
        raise ValueError("Domain name is too long.")

    labels = domain.split(".")

    if len(labels) < 2:
        raise ValueError("Enter a full domain, such as example.com.")

    for label in labels:
        if (
            not label
            or len(label) > 63
            or not re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?",
                label,
            )
        ):
            raise ValueError("Invalid domain format. Example: example.com")

    return domain


def make_resolution_steps(domain, record_type, records, cache_hit):
    """Build an educational explanation of the DNS lookup process."""
    if cache_hit:
        return [
            {
                "stage": "1",
                "name": "Client",
                "detail": f"Request received for {domain}.",
                "status": "Completed",
            },
            {
                "stage": "2",
                "name": "Recursive Resolver / Cache",
                "detail": "A matching cached answer was found.",
                "status": "Cache hit",
            },
            {
                "stage": "3",
                "name": "Response",
                "detail": f"Returned {len(records)} {record_type} record(s).",
                "status": "Completed",
            },
        ]

    return [
        {
            "stage": "1",
            "name": "Client",
            "detail": f"Requests the {record_type} record for {domain}.",
            "status": "Completed",
        },
        {
            "stage": "2",
            "name": "Recursive Resolver",
            "detail": "Checks its cache and begins name resolution.",
            "status": "Simulated",
        },
        {
            "stage": "3",
            "name": "Root Name Server",
            "detail": "Directs the resolver towards the relevant TLD.",
            "status": "Simulated",
        },
        {
            "stage": "4",
            "name": "TLD Name Server",
            "detail": "Directs the resolver towards the authoritative server.",
            "status": "Simulated",
        },
        {
            "stage": "5",
            "name": "Authoritative Name Server",
            "detail": "Provides the illustrative DNS record.",
            "status": "Simulated",
        },
        {
            "stage": "6",
            "name": "Client Response",
            "detail": f"Returns {len(records)} {record_type} record(s).",
            "status": "Completed",
        },
    ]


def live_dns_lookup(domain, record_type):
    """Use the operating system resolver; this requires network/DNS access."""
    family = socket.AF_INET if record_type == "A" else socket.AF_INET6

    try:
        results = socket.getaddrinfo(
            domain,
            None,
            family=family,
            type=socket.SOCK_STREAM,
        )
        addresses = sorted({item[4][0] for item in results})

        valid_addresses = []
        for address in addresses:
            parsed = ipaddress.ip_address(address)
            if record_type == "A" and parsed.version == 4:
                valid_addresses.append(address)
            elif record_type == "AAAA" and parsed.version == 6:
                valid_addresses.append(address)

        return valid_addresses
    except socket.gaierror:
        return []
    except OSError:
        return []


# -------------------- SESSION STATE --------------------
if "dns_cache" not in st.session_state:
    st.session_state.dns_cache = {}

if "query_history" not in st.session_state:
    st.session_state.query_history = []

if "last_result" not in st.session_state:
    st.session_state.last_result = None


# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.markdown("## 🌐 NetResolve")
    st.caption("DNS learning and diagnostics")
    st.divider()

    mode = st.radio(
        "Resolution mode",
        ["Demo Simulator", "Live System DNS"],
        help=(
            "Demo uses built-in illustrative records. Live mode asks "
            "your computer's configured DNS resolver."
        ),
    )

    st.markdown("### Quick domains")
    quick_domain = st.selectbox(
        "Choose an example",
        [
            "example.com",
            "google.com",
            "github.com",
            "openai.com",
            "wikipedia.org",
        ],
    )

    st.divider()
    st.markdown("### Session tools")

    if st.button("🧹 Clear DNS cache", use_container_width=True):
        st.session_state.dns_cache = {}
        st.session_state.last_result = None
        st.success("DNS cache cleared.")

    if st.button("🗑️ Clear query history", use_container_width=True):
        st.session_state.query_history = []
        st.success("Query history cleared.")

    st.divider()
    st.caption("Computer Networks • Project 5")


# -------------------- HEADER --------------------
st.markdown(
    """
    <div class="hero">
        <h1>🌐 DNS Resolution Simulator</h1>
        <p>
            Explore domain lookups, DNS records, resolver caching,
            and the journey from a domain name to an IP address.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

if mode == "Demo Simulator":
    st.info(
        "DEMO MODE: Built-in illustrative records are used. "
        "Root, TLD and authoritative server steps are simulated, "
        "not contacted over the network."
    )
else:
    st.warning(
        "LIVE SYSTEM DNS: Uses your computer's configured DNS resolver. "
        "Results can vary with your network and DNS settings."
    )


# -------------------- LOOKUP FORM --------------------
st.subheader("DNS Lookup")

with st.form("dns_lookup_form"):
    col_domain, col_type = st.columns([3, 1])

    with col_domain:
        domain_input = st.text_input(
            "Domain name",
            value=quick_domain,
            placeholder="example.com",
        )

    with col_type:
        record_type = st.selectbox(
            "Record type",
            ["A", "AAAA"],
            help="A = IPv4 address, AAAA = IPv6 address.",
        )

    submitted = st.form_submit_button(
        "🔍 Resolve Domain",
        use_container_width=True,
        type="primary",
    )

if submitted:
    try:
        domain = normalize_domain(domain_input)
        started = time.perf_counter()
        cache_key = (mode, domain, record_type)
        now = time.time()

        # Remove expired entries.
        expired_keys = [
            key for key, item in st.session_state.dns_cache.items()
            if item["expires_at"] <= now
        ]
        for key in expired_keys:
            del st.session_state.dns_cache[key]

        cache_item = st.session_state.dns_cache.get(cache_key)
        cache_hit = cache_item is not None

        if cache_hit:
            records = cache_item["records"]
            ttl = max(0, int(cache_item["expires_at"] - now))
        else:
            if mode == "Demo Simulator":
                demo_entry = DEMO_DNS.get(domain, {})
                records = demo_entry.get(record_type, [])
                ttl = demo_entry.get("TTL", 60)
            else:
                records = live_dns_lookup(domain, record_type)
                ttl = 60

            if records:
                st.session_state.dns_cache[cache_key] = {
                    "records": records,
                    "expires_at": now + ttl,
                    "created_at": now,
                }

        elapsed_ms = (time.perf_counter() - started) * 1000

        if records:
            steps = make_resolution_steps(
                domain, record_type, records, cache_hit
            )
            result = {
                "domain": domain,
                "record_type": record_type,
                "records": records,
                "ttl": ttl,
                "cache_hit": cache_hit,
                "elapsed_ms": round(elapsed_ms, 3),
                "mode": mode,
                "steps": steps,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "Success",
            }
            st.session_state.last_result = result
        else:
            st.session_state.last_result = {
                "domain": domain,
                "record_type": record_type,
                "records": [],
                "ttl": 0,
                "cache_hit": cache_hit,
                "elapsed_ms": round(elapsed_ms, 3),
                "mode": mode,
                "steps": [],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "Not found",
            }

        current = st.session_state.last_result
        st.session_state.query_history.insert(
            0,
            {
                "Time": current["timestamp"],
                "Domain": domain,
                "Type": record_type,
                "Mode": mode,
                "Status": current["status"],
                "Cache": "Hit" if cache_hit else "Miss",
                "Response (ms)": current["elapsed_ms"],
                "Records": ", ".join(records) if records else "-",
            },
        )
        st.session_state.query_history = (
            st.session_state.query_history[:100]
        )

    except ValueError as error:
        st.error(str(error))


# -------------------- RESULTS --------------------
result = st.session_state.last_result

if result:
    st.divider()
    st.subheader("Resolution Results")

    if result["status"] == "Success":
        st.success(f"Resolution successful for {result['domain']}")

        metric1, metric2, metric3, metric4 = st.columns(4)
        metric1.metric("Records Found", len(result["records"]))
        metric2.metric("Record Type", result["record_type"])
        metric3.metric("Response Time", f"{result['elapsed_ms']} ms")
        metric4.metric(
            "Cache Status",
            "HIT" if result["cache_hit"] else "MISS",
        )

        result_col, info_col = st.columns([2, 1])

        with result_col:
            st.markdown("#### Resolved IP Addresses")
            for address in result["records"]:
                st.code(address, language="text")

        with info_col:
            st.markdown("#### Lookup Details")
            st.write(f"**Domain:** {result['domain']}")
            st.write(f"**Mode:** {result['mode']}")
            st.write(f"**Record:** {result['record_type']}")
            st.write(f"**TTL:** {result['ttl']} seconds")
            st.write(
                f"**Cache:** {'Hit' if result['cache_hit'] else 'Miss'}"
            )

        st.divider()
        st.subheader("DNS Resolution Journey")

        st.caption(
            "The stages below explain the typical lookup path. "
            "In demo mode, these are simulated educational steps."
        )

        for step in result["steps"]:
            st.markdown(
                f"""
                <div class="step-card">
                    <h4>{step['stage']}. {step['name']}</h4>
                    <p>{step['detail']}</p>
                    <p><b>Status:</b> {step['status']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                "<div style='text-align:center;color:#5eead4;"
                "font-size:20px;'>↓</div>",
                unsafe_allow_html=True,
            )

    else:
        st.error(
            f"No {result['record_type']} record found for "
            f"{result['domain']} in the selected mode."
        )
        if result["mode"] == "Demo Simulator":
            st.info(
                "Demo mode supports example.com, google.com, github.com, "
                "openai.com and wikipedia.org. Choose a listed domain, "
                "or switch to Live System DNS for a real lookup."
            )
        else:
            st.info(
                "Check the domain and internet/DNS connection. "
                "Your network may block DNS lookups."
            )


# -------------------- QUERY HISTORY --------------------
st.divider()
st.subheader("Query History")

history = st.session_state.query_history

if history:
    history_df = pd.DataFrame(history)
    st.dataframe(
        history_df,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇️ Download Query History (CSV)",
        data=history_df.to_csv(index=False).encode("utf-8"),
        file_name="dns_query_history.csv",
        mime="text/csv",
    )
else:
    st.caption("No lookups yet. Resolve a domain to create query history.")

# -------------------- FOOTER --------------------
st.divider()
st.caption(
    "NetResolve • Computer Networks Project 5 • "
    "Demo IPs use documentation-only address ranges. "
    "Live DNS results depend on your configured resolver."
)
