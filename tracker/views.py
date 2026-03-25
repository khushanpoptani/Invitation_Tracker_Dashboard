import csv
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from .forms import (
    BulkStatusCSVUploadForm,
    CSVUploadForm,
    FollowUpTemplateBulkUploadForm,
    FollowUpTemplateForm,
    MessageTypeCreateForm,
    MessageTypeForm,
    StatusSearchForm,
    TrackerUserCreateForm,
    TrackerUserUpdateForm,
    UserFilterForm,
)
from .models import ConnectionStatus, FollowUpMessage, MessageType, SentConnection

User = get_user_model()
NAME_PREFIXES = {
    "mr",
    "mr.",
    "mrs",
    "mrs.",
    "ms",
    "ms.",
    "miss",
    "dr",
    "dr.",
    "prof",
    "prof.",
    "sir",
    "madam",
    "mx",
    "mx.",
}


def parse_filter_date(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None

    parsed = parse_date(value)
    if parsed:
        return parsed

    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    return None


def follow_up_sent_count_expression():
    return (
        Case(When(follow_up_sent_date_1__isnull=False, then=Value(1)), default=Value(0), output_field=IntegerField())
        + Case(When(follow_up_sent_date_2__isnull=False, then=Value(1)), default=Value(0), output_field=IntegerField())
        + Case(When(follow_up_sent_date_3__isnull=False, then=Value(1)), default=Value(0), output_field=IntegerField())
    )


def follow_up_sent_query(start_date=None, end_date=None):
    query = Q()
    for field_name in ("follow_up_sent_date_1", "follow_up_sent_date_2", "follow_up_sent_date_3"):
        field_query = Q(**{f"{field_name}__isnull": False})
        if start_date:
            field_query &= Q(**{f"{field_name}__gte": start_date})
        if end_date:
            field_query &= Q(**{f"{field_name}__lte": end_date})
        query |= field_query
    return query


def status_event_date_query(start_date=None, end_date=None):
    status_query = Q(status_date__isnull=False)
    fallback_query = Q(status_date__isnull=True)
    if start_date:
        status_query &= Q(status_date__gte=start_date)
        fallback_query &= Q(date__gte=start_date)
    if end_date:
        status_query &= Q(status_date__lte=end_date)
        fallback_query &= Q(date__lte=end_date)
    return status_query | fallback_query


def normalize_choice(value, valid_choices, default):
    return value if value in valid_choices else default


def start_of_week(day):
    return day - timedelta(days=day.weekday())


def start_of_month(day):
    return day.replace(day=1)


def end_of_month(day):
    return day.replace(day=monthrange(day.year, day.month)[1])


def shift_month(day, months):
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    day_of_month = min(day.day, monthrange(year, month)[1])
    return date(year, month, day_of_month)


def start_of_quarter(day):
    quarter_month = ((day.month - 1) // 3) * 3 + 1
    return date(day.year, quarter_month, 1)


def shift_year_safe(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def resolve_named_period(period_key, today):
    labels = {
        "this_week": "This Week",
        "last_week": "Last Week",
        "this_month": "This Month",
        "last_month": "Last Month",
        "last_30_days": "Last 30 Days",
        "previous_30_days": "Previous 30 Days",
        "this_quarter": "This Quarter",
        "last_quarter": "Last Quarter",
        "all_time": "All Time",
        "same_period_last_year": "Same Period Last Year",
    }

    if period_key == "this_week":
        return start_of_week(today), today, labels[period_key]

    if period_key == "last_week":
        last_week_end = start_of_week(today) - timedelta(days=1)
        return start_of_week(last_week_end), last_week_end, labels[period_key]

    if period_key == "this_month":
        return start_of_month(today), today, labels[period_key]

    if period_key == "last_month":
        previous_month_end = start_of_month(today) - timedelta(days=1)
        return start_of_month(previous_month_end), previous_month_end, labels[period_key]

    if period_key == "last_30_days":
        return today - timedelta(days=29), today, labels[period_key]

    if period_key == "previous_30_days":
        end = today - timedelta(days=30)
        return end - timedelta(days=29), end, labels[period_key]

    if period_key == "this_quarter":
        return start_of_quarter(today), today, labels[period_key]

    if period_key == "last_quarter":
        last_quarter_end = start_of_quarter(today) - timedelta(days=1)
        return start_of_quarter(last_quarter_end), last_quarter_end, labels[period_key]

    if period_key == "same_period_last_year":
        current_month_start = start_of_month(today)
        compare_start = shift_year_safe(current_month_start, -1)
        current_span = (today - current_month_start).days
        return compare_start, compare_start + timedelta(days=current_span), labels[period_key]

    return None, None, labels["all_time"]


def previous_period_bounds(start_date, end_date):
    if not start_date or not end_date:
        return None, None
    span_days = (end_date - start_date).days + 1
    compare_end = start_date - timedelta(days=1)
    compare_start = compare_end - timedelta(days=span_days - 1)
    return compare_start, compare_end


def resolve_compare_period(compare_by, compare_target, current_start, current_end, today):
    if compare_by == "none":
        return None, None, "No Comparison"

    if compare_target and compare_target != "auto":
        compare_start, compare_end, compare_label = resolve_named_period(compare_target, today)
        return compare_start, compare_end, compare_label

    if compare_by == "previous_year" and current_start and current_end:
        compare_start = shift_year_safe(current_start, -1)
        compare_end = shift_year_safe(current_end, -1)
        return compare_start, compare_end, "Same Period Last Year"

    if current_start and current_end:
        compare_start, compare_end = previous_period_bounds(current_start, current_end)
        return compare_start, compare_end, "Previous Period"

    return None, None, "No Comparison"


def filter_connections_by_sent_date(queryset, start_date=None, end_date=None):
    if start_date:
        queryset = queryset.filter(date__gte=start_date)
    if end_date:
        queryset = queryset.filter(date__lte=end_date)
    return queryset


def connection_status_name(connection):
    status_obj = getattr(connection, "connection_status", None)
    return (status_obj.name if status_obj else "").strip().lower()


def follow_up_dates(connection):
    return [
        sent_date
        for sent_date in (
            connection.follow_up_sent_date_1,
            connection.follow_up_sent_date_2,
            connection.follow_up_sent_date_3,
        )
        if sent_date
    ]


def follow_up_event_count(connection):
    return len(follow_up_dates(connection))


def safe_rate(numerator, denominator):
    if not denominator:
        return 0.0
    return (numerator / denominator) * 100


def build_delta(current_value, compare_value, compare_label):
    if compare_value is None:
        return {
            "direction": "flat",
            "display": "No comparison",
            "compare_label": compare_label,
        }

    diff = current_value - compare_value
    if diff > 0:
        direction = "up"
        prefix = "up"
    elif diff < 0:
        direction = "down"
        prefix = "down"
    else:
        direction = "flat"
        prefix = "flat"

    if compare_value == 0:
        if current_value == 0:
            display = f"No change vs {compare_label}"
        else:
            display = f"New vs {compare_label}"
        return {
            "direction": direction,
            "display": display,
            "compare_label": compare_label,
        }

    delta_percent = abs(diff) / compare_value * 100
    return {
        "direction": direction,
        "display": f"{prefix} {delta_percent:.1f}% vs {compare_label}",
        "compare_label": compare_label,
    }


def build_rate_summary(title, value, compare_value, compare_label):
    delta = build_delta(value, compare_value, compare_label)
    if compare_value is None:
        note = "Comparison not available for this selection."
    else:
        difference = value - compare_value
        if difference > 0:
            note = f"Up {abs(difference):.1f} pts vs {compare_label}"
        elif difference < 0:
            note = f"Down {abs(difference):.1f} pts vs {compare_label}"
        else:
            note = f"Flat vs {compare_label}"

    return {
        "title": title,
        "value": value,
        "delta": delta,
        "note": note,
    }


def summarize_connections(connections):
    sent_count = len(connections)
    accepted_count = 0
    follow_up_events_count = 0
    follow_up_connection_count = 0
    responded_count = 0
    pending_count = 0

    for connection in connections:
        status_name = connection_status_name(connection)
        if status_name == "accepted":
            accepted_count += 1
        elif status_name == "pending":
            pending_count += 1

        current_follow_up_events = follow_up_event_count(connection)
        follow_up_events_count += current_follow_up_events
        if current_follow_up_events:
            follow_up_connection_count += 1

        if connection.responded:
            responded_count += 1

    accepted_not_responded = sum(
        1
        for connection in connections
        if connection_status_name(connection) == "accepted" and not connection.responded
    )
    pending_like_count = max(sent_count - responded_count - accepted_not_responded, 0)

    return {
        "sent": sent_count,
        "accepted": accepted_count,
        "follow_up_events": follow_up_events_count,
        "follow_up_connections": follow_up_connection_count,
        "responded": responded_count,
        "pending": pending_count,
        "accepted_not_responded": accepted_not_responded,
        "pending_like": pending_like_count,
        "acceptance_rate": safe_rate(accepted_count, sent_count),
        "follow_up_rate": safe_rate(follow_up_events_count, sent_count),
        "response_rate": safe_rate(responded_count, sent_count),
    }


def bucket_start(day, grouping):
    if grouping == "weekly":
        return start_of_week(day)
    if grouping == "monthly":
        return day.replace(day=1)
    return day


def next_bucket(day, grouping):
    if grouping == "weekly":
        return day + timedelta(days=7)
    if grouping == "monthly":
        return shift_month(day, 1).replace(day=1)
    return day + timedelta(days=1)


def format_bucket_label(day, grouping):
    if grouping == "weekly":
        return f"Week of {day.strftime('%d %b')}"
    if grouping == "monthly":
        return day.strftime("%b %Y")
    return day.strftime("%d %b")


def build_trend_payload(connections, current_start, current_end, today):
    if connections:
        valid_dates = [connection.date for connection in connections if connection.date]
        start_date = current_start or min(valid_dates)
        end_date = current_end or max(valid_dates)
    else:
        end_date = today
        start_date = today - timedelta(days=29)

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    trim_limits = {"daily": 60, "weekly": 26, "monthly": 18}
    payload = {}

    for grouping in ("daily", "weekly", "monthly"):
        buckets = []
        bucket_values = {}
        cursor = bucket_start(start_date, grouping)
        final_bucket = bucket_start(end_date, grouping)

        while cursor <= final_bucket:
            bucket_values[cursor] = {"sent": 0, "accepted": 0, "follow_up": 0, "responded": 0}
            buckets.append(cursor)
            cursor = next_bucket(cursor, grouping)

        for connection in connections:
            if not connection.date:
                continue

            key = bucket_start(connection.date, grouping)
            if key not in bucket_values:
                continue

            bucket_values[key]["sent"] += 1
            if connection_status_name(connection) == "accepted":
                bucket_values[key]["accepted"] += 1
            bucket_values[key]["follow_up"] += follow_up_event_count(connection)
            if connection.responded:
                bucket_values[key]["responded"] += 1

        labels = [format_bucket_label(bucket, grouping) for bucket in buckets]
        datasets = {
            "sent": [bucket_values[bucket]["sent"] for bucket in buckets],
            "accepted": [bucket_values[bucket]["accepted"] for bucket in buckets],
            "follow_up": [bucket_values[bucket]["follow_up"] for bucket in buckets],
            "responded": [bucket_values[bucket]["responded"] for bucket in buckets],
        }

        trim_size = trim_limits[grouping]
        if len(labels) > trim_size:
            labels = labels[-trim_size:]
            for key, values in datasets.items():
                datasets[key] = values[-trim_size:]

        payload[grouping] = {
            "labels": labels,
            "datasets": datasets,
        }

    return payload


def build_user_metric_rows(connections, active_users, selected_user):
    rows_by_user = {
        user.id: {
            "id": user.id,
            "label": user.get_full_name().strip() or user.username,
            "subtext": f"@{user.username}",
            "sent": 0,
            "accepted": 0,
            "follow_up": 0,
            "responded": 0,
            "acceptance_rate": 0.0,
            "response_rate": 0.0,
            "is_selected": bool(selected_user and user.id == selected_user.id),
        }
        for user in active_users
    }

    for connection in connections:
        user_metrics = rows_by_user.get(connection.user_id)
        if not user_metrics:
            continue

        user_metrics["sent"] += 1
        if connection_status_name(connection) == "accepted":
            user_metrics["accepted"] += 1
        user_metrics["follow_up"] += follow_up_event_count(connection)
        if connection.responded:
            user_metrics["responded"] += 1

    rows = []
    for user_id, row in rows_by_user.items():
        row["acceptance_rate"] = safe_rate(row["accepted"], row["sent"])
        row["response_rate"] = safe_rate(row["responded"], row["sent"])
        if row["sent"] or row["is_selected"]:
            rows.append(row)

    rows.sort(key=lambda row: (-row["sent"], row["label"].lower()))
    return rows


def build_breakdown_rows(connections, group_by):
    grouped_rows = {}

    def get_group_key(connection):
        if group_by == "message":
            message_id = (connection.message_id or "").strip()
            return message_id or "__blank__"
        return connection.user_id

    def get_group_label(connection):
        if group_by == "message":
            return (connection.message_id or "").strip() or "Unassigned"
        return connection.user.get_full_name().strip() or connection.user.username

    def get_group_subtext(connection):
        if group_by == "message":
            return "Message ID"
        return f"@{connection.user.username}"

    for connection in connections:
        group_key = get_group_key(connection)
        row = grouped_rows.setdefault(
            group_key,
            {
                "label": get_group_label(connection),
                "subtext": get_group_subtext(connection),
                "sent": 0,
                "accepted": 0,
                "follow_up": 0,
                "responded": 0,
            },
        )

        row["sent"] += 1
        if connection_status_name(connection) == "accepted":
            row["accepted"] += 1
        row["follow_up"] += follow_up_event_count(connection)
        if connection.responded:
            row["responded"] += 1

    rows = []
    for row in grouped_rows.values():
        row["acceptance_rate"] = safe_rate(row["accepted"], row["sent"])
        row["response_rate"] = safe_rate(row["responded"], row["sent"])
        rows.append(row)

    rows.sort(key=lambda row: (-row["sent"], row["label"].lower()))
    return rows


def format_period_range(start_date, end_date):
    if start_date and end_date:
        return f"{start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}"
    if start_date:
        return f"From {start_date.strftime('%d %b %Y')}"
    if end_date:
        return f"Until {end_date.strftime('%d %b %Y')}"
    return "All available connection history"


def build_message_options(connections_queryset, user=None):
    message_ids = [
        item["message_id"]
        for item in connections_queryset.exclude(message_id="").values("message_id").distinct().order_by("message_id")
    ]
    if not message_ids:
        return []

    message_type_queryset = MessageType.objects.filter(message_id__in=message_ids)
    if user is not None:
        message_type_queryset = message_type_queryset.filter(user=user)

    message_type_map = {}
    for message_id, message in message_type_queryset.values_list("message_id", "message").order_by("message_id", "id"):
        message_type_map.setdefault(message_id, message)

    connection_message_map = {}
    for message_id, message in (
        connections_queryset.exclude(message_id="").exclude(message="").values_list("message_id", "message").order_by("message_id", "id")
    ):
        connection_message_map.setdefault(message_id, message)

    options = []
    for message_id in message_ids:
        raw_message = message_type_map.get(message_id) or connection_message_map.get(message_id) or ""
        one_line_message = " ".join(raw_message.split())
        preview = one_line_message[:80] + ("..." if len(one_line_message) > 80 else "")
        options.append(
            {
                "message_id": message_id,
                "message_text": one_line_message,
                "message_preview": preview,
            }
        )

    return options


def build_user_message_options(user):
    if not user:
        return []

    message_ids = list(
        {
            message_id
            for message_id in MessageType.objects.filter(user=user).exclude(message_id="").values_list("message_id", flat=True)
        }
        | {
            message_id
            for message_id in SentConnection.objects.filter(user=user).exclude(message_id="").values_list("message_id", flat=True)
        }
    )
    message_ids.sort()

    if not message_ids:
        return []

    message_type_map = {}
    for message_id, message in MessageType.objects.filter(user=user, message_id__in=message_ids).values_list(
        "message_id", "message"
    ).order_by("message_id", "id"):
        message_type_map.setdefault(message_id, message)

    connection_message_map = {}
    for message_id, message in SentConnection.objects.filter(user=user, message_id__in=message_ids).exclude(
        message=""
    ).values_list("message_id", "message").order_by("message_id", "id"):
        connection_message_map.setdefault(message_id, message)

    options = []
    for message_id in message_ids:
        raw_message = message_type_map.get(message_id) or connection_message_map.get(message_id) or ""
        one_line_message = " ".join(raw_message.split())
        preview = one_line_message[:80] + ("..." if len(one_line_message) > 80 else "")
        options.append(
            {
                "message_id": message_id,
                "message_text": one_line_message,
                "message_preview": preview,
            }
        )

    return options


def build_selected_message_label(message_id, message_options):
    if not message_id:
        return "All Message IDs"

    for option in message_options:
        if option["message_id"] == message_id:
            label = option["message_id"]
            if option["message_preview"]:
                label += f" - {option['message_preview']}"
            return label

    return "All Message IDs"


def extract_follow_up_first_name(full_name):
    tokens = [
        token.strip(" ,.-")
        for token in re.split(r"\s+", (full_name or "").strip())
        if token.strip(" ,.-")
    ]
    tokens = [token for token in tokens if token.lower() not in NAME_PREFIXES]

    if not tokens:
        return "there"

    first_candidate = tokens[0]
    if len(first_candidate) > 3:
        return first_candidate

    last_candidate = tokens[-1]
    if len(last_candidate) > 3:
        return last_candidate

    for token in tokens[1:]:
        if len(token) > 3:
            return token

    return "there"


def render_follow_up_template(template_text, full_name):
    return (template_text or "").replace("$first_name", extract_follow_up_first_name(full_name))


def apply_follow_up_template_to_connection(connection, template_obj, save=True):
    updated_fields = []

    if connection.follow_up_message_id != template_obj.id:
        connection.follow_up_message = template_obj
        updated_fields.append("follow_up_message")

    template_pairs = [
        ("follow_up_message_1", "follow_up_sent_date_1"),
        ("follow_up_message_2", "follow_up_sent_date_2"),
        ("follow_up_message_3", "follow_up_sent_date_3"),
    ]

    for message_field, sent_date_field in template_pairs:
        rendered_value = render_follow_up_template(getattr(template_obj, message_field), connection.name)
        if getattr(connection, sent_date_field) is None and getattr(connection, message_field) != rendered_value:
            setattr(connection, message_field, rendered_value)
            updated_fields.append(message_field)

    if save and updated_fields:
        connection.save(update_fields=updated_fields + ["updated_at"])

    return updated_fields


def sync_follow_up_template_to_connections(template_obj):
    accepted_status = ConnectionStatus.objects.filter(name__iexact="Accepted").first()
    if not accepted_status:
        return 0

    updated_count = 0
    matching_connections = SentConnection.objects.filter(
        user=template_obj.user,
        message_id=template_obj.message_id,
        connection_status=accepted_status,
    )
    for connection in matching_connections:
        if apply_follow_up_template_to_connection(connection, template_obj, save=True):
            updated_count += 1

    return updated_count


@login_required
def dashboard(request):
    today = timezone.localdate()
    active_users = list(User.objects.filter(is_active=True).order_by("username"))
    valid_user_values = {"all"} | {str(user.id) for user in active_users}
    valid_date_ranges = {
        "this_week",
        "last_week",
        "this_month",
        "last_month",
        "last_30_days",
        "this_quarter",
        "all_time",
        "custom",
    }
    valid_compare_by_values = {"previous_period", "previous_year", "none"}
    valid_compare_target_values = {
        "auto",
        "last_week",
        "last_month",
        "previous_30_days",
        "last_quarter",
        "same_period_last_year",
    }
    valid_breakdown_values = {"user", "message"}

    selected_user_id = normalize_choice(request.GET.get("user", "all").strip() or "all", valid_user_values, "all")
    selected_date_range = normalize_choice(
        request.GET.get("date_range", "this_month").strip() or "this_month",
        valid_date_ranges,
        "this_month",
    )
    selected_compare_by = normalize_choice(
        request.GET.get("compare_by", "previous_period").strip() or "previous_period",
        valid_compare_by_values,
        "previous_period",
    )
    selected_compare_target = normalize_choice(
        request.GET.get("compare_target", "auto").strip() or "auto",
        valid_compare_target_values,
        "auto",
    )
    breakdown_by = normalize_choice(
        request.GET.get("breakdown", "user").strip() or "user",
        valid_breakdown_values,
        "user",
    )

    selected_user = next((user for user in active_users if str(user.id) == selected_user_id), None)

    filter_scope = SentConnection.objects.select_related("user", "connection_status")
    if selected_user is not None:
        filter_scope = filter_scope.filter(user=selected_user)

    message_options = build_message_options(filter_scope, user=selected_user)
    valid_message_ids = {option["message_id"] for option in message_options}
    selected_message_id = request.GET.get("message_id", "").strip()
    if selected_message_id not in valid_message_ids:
        selected_message_id = ""

    if selected_message_id:
        filter_scope = filter_scope.filter(message_id=selected_message_id)

    custom_from = parse_filter_date(request.GET.get("custom_from", "").strip())
    custom_to = parse_filter_date(request.GET.get("custom_to", "").strip())
    if custom_from and custom_to and custom_from > custom_to:
        custom_from, custom_to = custom_to, custom_from

    if selected_date_range == "custom":
        current_start, current_end, current_period_label = custom_from, custom_to, "Custom Range"
    else:
        current_start, current_end, current_period_label = resolve_named_period(selected_date_range, today)

    compare_start, compare_end, compare_period_label = resolve_compare_period(
        selected_compare_by,
        selected_compare_target,
        current_start,
        current_end,
        today,
    )

    current_connections = list(filter_connections_by_sent_date(filter_scope, current_start, current_end))
    compare_connections = (
        list(filter_connections_by_sent_date(filter_scope, compare_start, compare_end))
        if compare_start or compare_end
        else []
    )

    current_summary = summarize_connections(current_connections)
    compare_summary = summarize_connections(compare_connections) if compare_connections else None

    compare_sent = compare_summary["sent"] if compare_summary else None
    compare_accepted = compare_summary["accepted"] if compare_summary else None
    compare_follow_up = compare_summary["follow_up_events"] if compare_summary else None
    compare_responded = compare_summary["responded"] if compare_summary else None

    kpi_cards = [
        {
            "title": "Connections Sent",
            "value": current_summary["sent"],
            "icon": "bi-send-check",
            "tone": "slate",
            "delta": build_delta(current_summary["sent"], compare_sent, compare_period_label),
        },
        {
            "title": "Connections Accepted",
            "value": current_summary["accepted"],
            "icon": "bi-check2-circle",
            "tone": "green",
            "delta": build_delta(current_summary["accepted"], compare_accepted, compare_period_label),
        },
        {
            "title": "Follow-Ups Sent",
            "value": current_summary["follow_up_events"],
            "icon": "bi-envelope-paper-heart",
            "tone": "blue",
            "delta": build_delta(current_summary["follow_up_events"], compare_follow_up, compare_period_label),
        },
        {
            "title": "Responses Received",
            "value": current_summary["responded"],
            "icon": "bi-reply-all",
            "tone": "rose",
            "delta": build_delta(current_summary["responded"], compare_responded, compare_period_label),
        },
    ]

    status_total = max(current_summary["sent"], 1)
    donut_segments = [
        {
            "label": "Accepted",
            "value": current_summary["accepted_not_responded"],
            "color": "#2f8f6b",
            "percent": current_summary["accepted_not_responded"] / status_total * 100,
        },
        {
            "label": "Pending / Other",
            "value": current_summary["pending_like"],
            "color": "#f2b14f",
            "percent": current_summary["pending_like"] / status_total * 100,
        },
        {
            "label": "Responded",
            "value": current_summary["responded"],
            "color": "#3c6df0",
            "percent": current_summary["responded"] / status_total * 100,
        },
    ]

    donut_parts = []
    running_total = 0.0
    for segment in donut_segments:
        start_percent = running_total
        running_total += segment["percent"]
        donut_parts.append(f"{segment['color']} {start_percent:.2f}% {running_total:.2f}%")
    donut_style = ", ".join(donut_parts) if donut_parts else "#d9e3ef 0% 100%"

    funnel_steps = [
        {"label": "Sent", "value": current_summary["sent"]},
        {"label": "Accepted", "value": current_summary["accepted"]},
        {"label": "Follow-Up", "value": current_summary["follow_up_connections"]},
        {"label": "Responded", "value": current_summary["responded"]},
    ]
    funnel_base = max(current_summary["sent"], 1)
    for index, step in enumerate(funnel_steps):
        step["width"] = max((step["value"] / funnel_base) * 100, 8 if step["value"] else 0)
        previous_value = funnel_steps[index - 1]["value"] if index else step["value"]
        step["conversion_rate"] = safe_rate(step["value"], previous_value) if index and previous_value else 100.0

    trend_payload = build_trend_payload(current_connections, current_start, current_end, today)

    comparison_scope = SentConnection.objects.select_related("user", "connection_status")
    if selected_message_id:
        comparison_scope = comparison_scope.filter(message_id=selected_message_id)
    comparison_connections = list(filter_connections_by_sent_date(comparison_scope, current_start, current_end))
    user_metric_rows = build_user_metric_rows(comparison_connections, active_users, selected_user)

    breakdown_rows = build_breakdown_rows(current_connections, breakdown_by)

    export_mode = request.GET.get("download", "").strip().lower()

    if export_mode == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="dashboard_breakdown_{today.isoformat()}.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Message ID" if breakdown_by == "message" else "User",
                "Sent",
                "Accepted",
                "Follow Up",
                "Responded",
                "Acceptance %",
                "Response %",
            ]
        )
        for row in breakdown_rows:
            writer.writerow(
                [
                    row["label"],
                    row["sent"],
                    row["accepted"],
                    row["follow_up"],
                    row["responded"],
                    f"{row['acceptance_rate']:.1f}",
                    f"{row['response_rate']:.1f}",
                ]
            )
        return response

    rate_cards = [
        build_rate_summary(
            "Acceptance Rate",
            current_summary["acceptance_rate"],
            compare_summary["acceptance_rate"] if compare_summary else None,
            compare_period_label,
        ),
        build_rate_summary(
            "Follow-Up Rate",
            current_summary["follow_up_rate"],
            compare_summary["follow_up_rate"] if compare_summary else None,
            compare_period_label,
        ),
        build_rate_summary(
            "Response Rate",
            current_summary["response_rate"],
            compare_summary["response_rate"] if compare_summary else None,
            compare_period_label,
        ),
    ]

    template_name = "tracker/dashboard_pdf.html" if export_mode == "pdf" else "tracker/dashboard.html"

    return render(
        request,
        template_name,
        {
            "users": active_users,
            "selected_user_id": selected_user_id,
            "selected_date_range": selected_date_range,
            "selected_compare_by": selected_compare_by,
            "selected_compare_target": selected_compare_target,
            "selected_message_id": selected_message_id,
            "selected_message_label": build_selected_message_label(selected_message_id, message_options),
            "message_options": message_options,
            "current_period_label": current_period_label,
            "compare_period_label": compare_period_label,
            "current_period_range": format_period_range(current_start, current_end),
            "compare_period_range": format_period_range(compare_start, compare_end) if (compare_start or compare_end) else "Comparison unavailable",
            "today": today,
            "kpi_cards": kpi_cards,
            "donut_segments": donut_segments,
            "donut_style": donut_style,
            "status_total": current_summary["sent"],
            "funnel_steps": funnel_steps,
            "trend_payload": trend_payload,
            "user_metric_rows": user_metric_rows,
            "rate_cards": rate_cards,
            "breakdown_by": breakdown_by,
            "breakdown_rows": breakdown_rows,
            "selected_user_name": (
                selected_user.get_full_name().strip() or selected_user.username
                if selected_user
                else "All Users"
            ),
            "date_range_options": [
                ("this_week", "This Week"),
                ("last_week", "Last Week"),
                ("this_month", "This Month"),
                ("last_month", "Last Month"),
                ("last_30_days", "Last 30 Days"),
                ("this_quarter", "This Quarter"),
                ("all_time", "All Time"),
                ("custom", "Custom Date Range"),
            ],
            "compare_by_options": [
                ("previous_period", "Previous Period"),
                ("previous_year", "Same Period Last Year"),
                ("none", "No Comparison"),
            ],
            "compare_target_options": [
                ("auto", f"Auto ({compare_period_label})" if compare_period_label != "No Comparison" else "Auto"),
                ("last_week", "Last Week"),
                ("last_month", "Last Month"),
                ("previous_30_days", "Previous 30 Days"),
                ("last_quarter", "Last Quarter"),
                ("same_period_last_year", "Same Period Last Year"),
            ],
            "breakdown_options": [
                ("user", "By User"),
                ("message", "By Message ID"),
            ],
            "custom_from": custom_from.isoformat() if custom_from else "",
            "custom_to": custom_to.isoformat() if custom_to else "",
            "export_mode": export_mode,
        },
    )


@login_required
def sent_connections_list(request):
    users = User.objects.filter(is_active=True).order_by("username")
    selected_user_id = request.GET.get("user", "").strip()
    selected_message_id = request.GET.get("message_id", "").strip()
    selected_status_id = request.GET.get("status", "").strip()
    selected_follow_up_count = request.GET.get("follow_up_sent_count", "").strip()
    search_query = request.GET.get("search", "").strip()
    from_date_raw = request.GET.get("from_date", "").strip()
    to_date_raw = request.GET.get("to_date", "").strip()
    from_date = parse_filter_date(from_date_raw)
    to_date = parse_filter_date(to_date_raw)
    if from_date and to_date and from_date > to_date:
        from_date, to_date = to_date, from_date

    connections = (
        SentConnection.objects.select_related("user", "connection_status")
        .annotate(follow_up_sent_count=follow_up_sent_count_expression())
    )

    if selected_user_id:
        connections = connections.filter(user_id=selected_user_id)

    base_connections = connections
    message_options = build_message_options(base_connections)
    if selected_message_id and not any(option["message_id"] == selected_message_id for option in message_options):
        selected_message_id = ""

    if selected_message_id:
        connections = connections.filter(message_id=selected_message_id)

    if selected_status_id:
        connections = connections.filter(connection_status_id=selected_status_id)

    if selected_follow_up_count != "":
        try:
            follow_up_count_value = int(selected_follow_up_count)
            connections = connections.filter(follow_up_sent_count=follow_up_count_value)
        except ValueError:
            selected_follow_up_count = ""

    if search_query:
        connections = connections.filter(
            Q(name__icontains=search_query)
            | Q(profile_link__icontains=search_query)
            | Q(message__icontains=search_query)
            | Q(message_id__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
        )

    if from_date:
        connections = connections.filter(date__gte=from_date)
    if to_date:
        connections = connections.filter(date__lte=to_date)

    status_options = ConnectionStatus.objects.order_by("id")
    selected_message_label = build_selected_message_label(selected_message_id, message_options)

    if request.GET.get("download") == "1":
        response = HttpResponse(content_type="text/csv")
        filename = f"sent_connections_filtered_{timezone.localdate().isoformat()}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Name",
                "Profile Link",
                "Message",
                "Message ID",
                "Date",
                "Status Date",
                "Status",
                "Responded",
                "Follow Up Sent Count",
                "Follow Up 1",
                "Follow Up 2",
                "Follow Up 3",
                "Follow Up Sent Date 1",
                "Follow Up Sent Date 2",
                "Follow Up Sent Date 3",
                "User",
            ]
        )

        for row in connections.order_by("-date", "name"):
            writer.writerow(
                [
                    row.name,
                    row.profile_link,
                    row.message,
                    row.message_id,
                    row.date.isoformat() if row.date else "",
                    row.status_date.isoformat() if row.status_date else "",
                    row.connection_status.name if row.connection_status else "",
                    "True" if row.responded else "False",
                    row.follow_up_sent_count,
                    row.follow_up_message_1,
                    row.follow_up_message_2,
                    row.follow_up_message_3,
                    row.follow_up_sent_date_1.isoformat() if row.follow_up_sent_date_1 else "",
                    row.follow_up_sent_date_2.isoformat() if row.follow_up_sent_date_2 else "",
                    row.follow_up_sent_date_3.isoformat() if row.follow_up_sent_date_3 else "",
                    row.user.username if row.user else "",
                ]
            )

        return response

    context = {
        "connections": connections,
        "users": users,
        "message_options": message_options,
        "status_options": status_options,
        "selected_user_id": selected_user_id,
        "selected_message_id": selected_message_id,
        "selected_message_label": selected_message_label,
        "selected_status_id": selected_status_id,
        "selected_follow_up_count": selected_follow_up_count,
        "selected_search_query": search_query,
        "selected_from_date": from_date.isoformat() if from_date else "",
        "selected_to_date": to_date.isoformat() if to_date else "",
    }
    return render(request, "tracker/sent_connections_list.html", context)


@login_required
def message_type_list(request):
    user_filter_form = UserFilterForm(request.GET or None)
    message_types = MessageType.objects.select_related("user")

    if user_filter_form.is_valid() and user_filter_form.cleaned_data.get("user"):
        message_types = message_types.filter(user=user_filter_form.cleaned_data["user"])

    return render(
        request,
        "tracker/message_type_list.html",
        {"message_types": message_types, "user_filter_form": user_filter_form},
    )


def _next_message_id_for_user(user):
    latest = MessageType.objects.filter(user=user).order_by("-id").first()
    if not latest or not (latest.message_id or "").strip():
        return "1"

    message_id = latest.message_id.strip()
    if message_id.isdigit():
        return str(int(message_id) + 1)

    match = re.match(r"^(.*?)(\d+)$", message_id)
    if match:
        prefix, numeric_tail = match.groups()
        next_number = int(numeric_tail) + 1
        width = len(numeric_tail)
        return f"{prefix}{next_number:0{width}d}"

    return str(MessageType.objects.filter(user=user).count() + 1)


@login_required
def message_type_next_id(request):
    user_id = request.GET.get("user_id", "").strip()
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None

    if not user:
        return JsonResponse({"next_message_id": ""})

    return JsonResponse({"next_message_id": _next_message_id_for_user(user)})


@login_required
def message_type_create(request):
    form = MessageTypeCreateForm(request.POST or None)
    selected_user = None

    selected_user_id = (
        request.POST.get("user", "").strip() if request.method == "POST" else request.GET.get("user", "").strip()
    )
    if selected_user_id:
        selected_user = User.objects.filter(pk=selected_user_id, is_active=True).first()

    next_message_id = _next_message_id_for_user(selected_user) if selected_user else ""

    if request.method == "POST" and form.is_valid():
        user = form.cleaned_data["user"]
        message = form.cleaned_data["message"]
        message_id = _next_message_id_for_user(user)

        # Safety against concurrent inserts.
        while MessageType.objects.filter(user=user, message_id=message_id).exists():
            if message_id.isdigit():
                message_id = str(int(message_id) + 1)
            else:
                message_id = str(MessageType.objects.filter(user=user).count() + 1)

        MessageType.objects.create(user=user, message=message, message_id=message_id)
        messages.success(request, "Message type created.")
        return redirect("message_type_list")

    return render(
        request,
        "tracker/message_type_create.html",
        {
            "form": form,
            "title": "Add Message Type",
            "cancel_url": reverse("message_type_list"),
            "next_message_id": next_message_id,
        },
    )


@login_required
def message_type_edit(request, pk):
    message_type = get_object_or_404(MessageType, pk=pk)
    original_message_id = message_type.message_id
    original_user_id = message_type.user_id
    form = MessageTypeForm(request.POST or None, instance=message_type)
    form.fields["user"].disabled = True

    if request.method == "POST" and form.is_valid():
        updated_message_type = form.save(commit=False)
        updated_message_id = (updated_message_type.message_id or "").strip()
        updated_message_type.user_id = original_user_id

        try:
            with transaction.atomic():
                if updated_message_id != original_message_id:
                    conflicting_follow_up = FollowUpMessage.objects.filter(
                        user_id=original_user_id,
                        message_id=updated_message_id,
                    ).exclude(message_id=original_message_id)
                    if conflicting_follow_up.exists():
                        form.add_error(
                            "message_id",
                            "That Message ID already exists in Follow Up Templates for this user.",
                        )
                        raise ValueError("follow_up_conflict")

                    updated_message_type.save()

                    SentConnection.objects.filter(
                        user_id=original_user_id,
                        message_id=original_message_id,
                    ).update(
                        message_id=updated_message_id,
                        updated_at=timezone.now(),
                    )

                    FollowUpMessage.objects.filter(
                        user_id=original_user_id,
                        message_id=original_message_id,
                    ).update(
                        message_id=updated_message_id,
                        updated_at=timezone.now(),
                    )
                else:
                    updated_message_type.save()
        except ValueError as exc:
            if str(exc) != "follow_up_conflict":
                raise
        else:
            if updated_message_id != original_message_id:
                messages.success(
                    request,
                    "Message type updated. Sent Connections and Follow Up Templates were synced to the new Message ID.",
                )
            else:
                messages.success(request, "Message type updated.")
            return redirect("message_type_list")

    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": "Edit Message Type", "cancel_url": reverse("message_type_list")},
    )


@login_required
def message_type_delete(request, pk):
    message_type = get_object_or_404(MessageType, pk=pk)
    if request.method == "POST":
        message_type.delete()
        messages.success(request, "Message type deleted.")
        return redirect("message_type_list")
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "title": "Delete Message Type",
            "object_name": str(message_type),
            "cancel_url": reverse("message_type_list"),
        },
    )


@login_required
def follow_up_message_list(request):
    users = list(User.objects.filter(is_active=True).order_by("username"))
    selected_user_id = request.GET.get("user", "").strip()
    search_query = request.GET.get("search", "").strip()

    if not selected_user_id and users:
        selected_user_id = str(users[0].id)

    selected_user = next((user for user in users if str(user.id) == selected_user_id), None)
    create_form = FollowUpTemplateForm(initial={"user": selected_user} if selected_user else None)
    bulk_upload_form = FollowUpTemplateBulkUploadForm(initial={"user": selected_user} if selected_user else None)
    template_message_options = build_user_message_options(selected_user)
    selected_template_message_id = (
        (create_form["message_id"].value() if "message_id" in create_form.fields else "") if create_form else ""
    )
    selected_template_message_label = (
        build_selected_message_label(selected_template_message_id, template_message_options)
        if selected_template_message_id
        else "Select Message ID"
    )

    def redirect_with_filters(user_id="", search=""):
        params = {}
        if user_id:
            params["user"] = user_id
        if search:
            params["search"] = search

        redirect_url = reverse("follow_up_message_list")
        if params:
            redirect_url += f"?{urlencode(params)}"
        return HttpResponseRedirect(redirect_url)

    if request.method == "POST":
        action = request.POST.get("action", "").strip()
        current_user = request.POST.get("current_user", selected_user_id)
        current_search = request.POST.get("current_search", search_query)

        if action == "create":
            create_form = FollowUpTemplateForm(request.POST)
            selected_template_message_id = request.POST.get("message_id", "").strip()
            selected_template_message_label = (
                build_selected_message_label(selected_template_message_id, template_message_options)
                if selected_template_message_id
                else "Select Message ID"
            )
            if create_form.is_valid():
                template_obj = create_form.save()
                updated_count = sync_follow_up_template_to_connections(template_obj)
                success_message = f"Follow up template created for Message ID {template_obj.message_id}."
                if updated_count:
                    success_message += f" Updated {updated_count} accepted connection(s)."
                messages.success(request, success_message)
                return redirect_with_filters(str(template_obj.user_id), current_search)
            messages.error(request, "Could not create follow up template. Check the fields and try again.")

        elif action == "update":
            template_obj = get_object_or_404(FollowUpMessage, pk=request.POST.get("template_id"))
            updated_user = User.objects.filter(pk=request.POST.get("user", ""), is_active=True).first()
            updated_message_id = request.POST.get("message_id", "").strip()
            template_obj.follow_up_message_1 = request.POST.get("follow_up_message_1", "").strip()
            template_obj.follow_up_message_2 = request.POST.get("follow_up_message_2", "").strip()
            template_obj.follow_up_message_3 = request.POST.get("follow_up_message_3", "").strip()

            if not updated_user or not updated_message_id:
                messages.error(request, "User and Message ID are required to update a follow up template.")
                return redirect_with_filters(current_user, current_search)

            duplicate_exists = FollowUpMessage.objects.filter(user=updated_user, message_id=updated_message_id).exclude(
                pk=template_obj.pk
            )
            if duplicate_exists.exists():
                messages.error(request, "That Message ID already has follow up messages for the selected user.")
                return redirect_with_filters(current_user, current_search)

            template_obj.user = updated_user
            template_obj.message_id = updated_message_id
            template_obj.save()
            updated_count = sync_follow_up_template_to_connections(template_obj)
            success_message = f"Follow up template updated for Message ID {template_obj.message_id}."
            if updated_count:
                success_message += f" Updated {updated_count} accepted connection(s)."
            messages.success(request, success_message)
            return redirect_with_filters(str(template_obj.user_id), current_search)

        elif action == "delete":
            template_obj = get_object_or_404(FollowUpMessage, pk=request.POST.get("template_id"))
            template_user_id = str(template_obj.user_id)
            template_message_id = template_obj.message_id
            template_obj.delete()
            messages.success(request, f"Follow up template deleted for Message ID {template_message_id}.")
            return redirect_with_filters(template_user_id, current_search)

        elif action == "bulk_upload":
            bulk_upload_form = FollowUpTemplateBulkUploadForm(request.POST, request.FILES)
            if bulk_upload_form.is_valid():
                csv_file = bulk_upload_form.cleaned_data["csv_file"]
                user = bulk_upload_form.cleaned_data["user"]

                try:
                    decoded = csv_file.read().decode("utf-8-sig").splitlines()
                    reader = csv.DictReader(decoded)
                except UnicodeDecodeError:
                    messages.error(request, "CSV must be UTF-8 encoded.")
                    return redirect_with_filters(str(user.id), current_search)

                if not reader.fieldnames:
                    messages.error(request, "CSV header row is missing.")
                    return redirect_with_filters(str(user.id), current_search)

                normalized_headers = {
                    field.strip().lower().replace(" ", "_")
                    for field in reader.fieldnames
                    if field
                }
                required_columns = {"message_id"}
                if not required_columns.issubset(normalized_headers):
                    messages.error(request, "CSV must contain at least the `message_id` column.")
                    return redirect_with_filters(str(user.id), current_search)

                created_count = 0
                updated_count = 0
                failed_rows = []

                for line_number, row in enumerate(reader, start=2):
                    normalized = {
                        k.strip().lower().replace(" ", "_"): (v or "").strip()
                        for k, v in row.items()
                        if k
                    }
                    message_id = normalized.get("message_id", "")
                    if not message_id:
                        failed_rows.append(f"Row {line_number}: message_id is required")
                        continue

                    template_obj, created = FollowUpMessage.objects.update_or_create(
                        user=user,
                        message_id=message_id,
                        defaults={
                            "follow_up_message_1": normalized.get("follow_up_message_1", ""),
                            "follow_up_message_2": normalized.get("follow_up_message_2", ""),
                            "follow_up_message_3": normalized.get("follow_up_message_3", ""),
                        },
                    )
                    sync_follow_up_template_to_connections(template_obj)
                    created_count += int(created)
                    updated_count += int(not created)

                if created_count or updated_count:
                    messages.success(
                        request,
                        f"Bulk upload complete. Created {created_count} template(s) and updated {updated_count} template(s).",
                    )
                if failed_rows:
                    messages.warning(request, "Some rows failed: " + " | ".join(failed_rows[:5]))
                return redirect_with_filters(str(user.id), current_search)

            messages.error(request, "Could not upload follow up templates. Check the file and try again.")

    templates = FollowUpMessage.objects.select_related("user")
    if selected_user:
        templates = templates.filter(user=selected_user)
    if search_query:
        templates = templates.filter(
            Q(message_id__icontains=search_query)
            | Q(follow_up_message_1__icontains=search_query)
            | Q(follow_up_message_2__icontains=search_query)
            | Q(follow_up_message_3__icontains=search_query)
        )

    return render(
        request,
        "tracker/follow_up_message_list.html",
        {
            "users": users,
            "selected_user": selected_user,
            "selected_user_id": selected_user_id,
            "selected_search_query": search_query,
            "templates": templates,
            "create_form": create_form,
            "bulk_upload_form": bulk_upload_form,
            "template_message_options": template_message_options,
            "selected_template_message_id": selected_template_message_id,
            "selected_template_message_label": selected_template_message_label,
        },
    )


def _parse_csv_date(raw_date):
    cleaned = (raw_date or "").strip()
    if not cleaned:
        return None

    parsed = parse_date(cleaned)
    if parsed:
        return parsed

    for fmt in ["%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%m-%d-%Y"]:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    return None


def get_or_create_connection_status(status_name):
    status = ConnectionStatus.objects.filter(name__iexact=status_name).first()
    if status is None:
        status = ConnectionStatus.objects.create(name=status_name)
    return status

@login_required
def download_sample_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="sample_sent_connections.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "name",
            "profile_link",
            "message",
            "message_format",
            "date",
        ]
    )
    writer.writerow(
        [
            "John Doe",
            "https://www.linkedin.com/in/john-doe",
            "Hi John, I wanted to send a quick follow up on my connection request.",
            "Hi $first_name, I wanted to send a quick follow up on my connection request.",
            "2026-02-27",
        ]
    )
    return response


@login_required
def download_follow_up_template_sample_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="sample_follow_up_templates.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "message_id",
            "follow_up_message_1",
            "follow_up_message_2",
            "follow_up_message_3",
        ]
    )
    writer.writerow(
        [
            "MSG001",
            "Hi $first_name, just following up on my previous message.",
            "Checking in again, $first_name. Happy to connect if useful.",
            "Final follow up, $first_name. Let me know if this is relevant.",
        ]
    )
    return response


@login_required
def download_bulk_status_missing_csv(request):
    missing_rows = request.session.get("bulk_status_missing_rows", [])

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="bulk_status_missing_users.csv"'

    writer = csv.writer(response)
    writer.writerow(["Name", "Date Added", "Account", "Geography", "Outreach activity", "Source File"])
    for row in missing_rows:
        writer.writerow(
            [
                row.get("name", ""),
                row.get("date_added", ""),
                row.get("account", ""),
                row.get("geography", ""),
                row.get("outreach_activity", ""),
                row.get("source_file", ""),
            ]
        )

    return response


@login_required
def download_bulk_status_sample_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="sample_bulk_update_connections.csv"'

    writer = csv.writer(response)
    writer.writerow(["Name", "Date Added", "Account", "Geography", "Outreach activity", "Source File"])
    writer.writerow(
        [
            "John Doe",
            "2026-03-18",
            "Example Account",
            "North America",
            "Accepted invite",
            "accepted_connections.csv",
        ]
    )
    return response


@login_required
def bulk_update_connections(request):
    form = BulkStatusCSVUploadForm(request.POST or None, request.FILES or None)
    updated_rows = []
    missing_rows = []
    failed_rows = []

    if request.method == "POST" and form.is_valid():
        csv_file = form.cleaned_data["csv_file"]
        user = form.cleaned_data["user"]

        try:
            decoded = csv_file.read().decode("utf-8-sig").splitlines()
            reader = csv.DictReader(decoded)
        except UnicodeDecodeError:
            messages.error(request, "CSV must be UTF-8 encoded.")
            return redirect("bulk_update_connections")

        if not reader.fieldnames:
            messages.error(request, "CSV header row is missing.")
            return redirect("bulk_update_connections")

        normalized_headers = {
            field.strip().lower().replace(" ", "_")
            for field in reader.fieldnames
            if field
        }
        required_columns = {"name", "date_added"}
        if not required_columns.issubset(normalized_headers):
            messages.error(request, "CSV must contain headers: Name and Date Added.")
            return redirect("bulk_update_connections")

        accepted_status = get_or_create_connection_status("Accepted")

        for line_number, row in enumerate(reader, start=2):
            normalized = {
                k.strip().lower().replace(" ", "_"): (v or "").strip()
                for k, v in row.items()
                if k
            }
            name = normalized.get("name", "")
            raw_date_added = normalized.get("date_added", "")

            if not name:
                failed_rows.append(
                    {
                        "name": "",
                        "reason": f"Row {line_number}: Name is required",
                    }
                )
                continue

            status_date = _parse_csv_date(raw_date_added)
            if not status_date:
                failed_rows.append(
                    {
                        "name": name,
                        "reason": f"Row {line_number}: Invalid Date Added '{raw_date_added}'",
                    }
                )
                continue

            matching_connections = list(SentConnection.objects.filter(user=user, name__iexact=name).order_by("-id"))
            if not matching_connections:
                missing_rows.append(
                    {
                        "name": name,
                        "date_added": raw_date_added,
                        "account": normalized.get("account", ""),
                        "geography": normalized.get("geography", ""),
                        "outreach_activity": normalized.get("outreach_activity", ""),
                        "source_file": normalized.get("source_file", ""),
                    }
                )
                continue

            for connection in matching_connections:
                connection.connection_status = accepted_status
                connection.status_date = status_date

                update_fields = ["connection_status", "status_date", "updated_at"]
                follow_up_message = FollowUpMessage.objects.filter(
                    user=connection.user,
                    message_id=connection.message_id,
                ).first()
                if follow_up_message:
                    apply_follow_up_template_to_connection(connection, follow_up_message, save=False)
                    update_fields.extend(
                        ["follow_up_message", "follow_up_message_1", "follow_up_message_2", "follow_up_message_3"]
                    )

                connection.save(update_fields=list(dict.fromkeys(update_fields)))
                updated_rows.append(
                    {
                        "name": connection.name,
                        "status_date": status_date.isoformat(),
                        "message_id": connection.message_id,
                    }
                )

        request.session["bulk_status_missing_rows"] = missing_rows

        if updated_rows:
            messages.success(request, f"Updated {len(updated_rows)} connection record(s) to Accepted.")
        if missing_rows:
            messages.warning(request, f"{len(missing_rows)} row(s) were not found for the selected user.")
        if failed_rows:
            messages.warning(request, "Some rows were skipped: " + " | ".join(row["reason"] for row in failed_rows[:5]))

        form = BulkStatusCSVUploadForm(initial={"user": user})

    return render(
        request,
        "tracker/bulk_update_connections.html",
        {
            "form": form,
            "updated_rows": updated_rows,
            "missing_rows": missing_rows,
            "failed_rows": failed_rows,
        },
    )


@login_required
def upload_sent_connections_csv(request):
    form = CSVUploadForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        csv_file = form.cleaned_data["csv_file"]
        user = form.cleaned_data["user"]

        try:
            decoded = csv_file.read().decode("utf-8-sig").splitlines()
            reader = csv.DictReader(decoded)
        except UnicodeDecodeError:
            messages.error(request, "CSV must be UTF-8 encoded.")
            return redirect("upload_sent_connections_csv")

        required_columns = {"name", "profile_link", "message", "message_format", "date"}
        if not reader.fieldnames:
            messages.error(request, "CSV header row is missing.")
            return redirect("upload_sent_connections_csv")

        normalized_headers = {
            field.strip().lower().replace(" ", "_")
            for field in reader.fieldnames
            if field
        }
        if not required_columns.issubset(normalized_headers):
            messages.error(
                request,
                "CSV must contain headers: name, profile_link, message, message_format, date.",
            )
            return redirect("upload_sent_connections_csv")

        pending_status = ConnectionStatus.objects.filter(name__iexact="Pending").first()
        if pending_status is None:
            pending_status = ConnectionStatus.objects.create(name="Pending")

        created_count = 0
        created_message_type_count = 0
        failed_rows = []
        message_type_cache = {
            message_text.strip(): message_id
            for message_text, message_id in MessageType.objects.filter(user=user)
            .exclude(message="")
            .values_list("message", "message_id")
        }

        for line_number, row in enumerate(reader, start=2):
            normalized = {
                k.strip().lower().replace(" ", "_"): (v or "").strip()
                for k, v in row.items()
                if k
            }
            name = normalized.get("name", "")
            raw_date = normalized.get("date", "")
            message_format = normalized.get("message_format", "")

            if not name:
                failed_rows.append(f"Row {line_number}: name is required")
                continue

            if not message_format:
                failed_rows.append(f"Row {line_number}: message_format is required")
                continue

            parsed_date = _parse_csv_date(raw_date)
            if not parsed_date:
                failed_rows.append(f"Row {line_number}: invalid date '{raw_date}'")
                continue

            message_id = message_type_cache.get(message_format)
            if not message_id:
                message_id = _next_message_id_for_user(user)
                while MessageType.objects.filter(user=user, message_id=message_id).exists():
                    if message_id.isdigit():
                        message_id = str(int(message_id) + 1)
                    else:
                        message_id = str(MessageType.objects.filter(user=user).count() + 1)

                MessageType.objects.create(
                    user=user,
                    message=message_format,
                    message_id=message_id,
                )
                message_type_cache[message_format] = message_id
                created_message_type_count += 1

            SentConnection.objects.create(
                name=name,
                profile_link=normalized.get("profile_link", ""),
                message=normalized.get("message", ""),
                message_id=message_id,
                date=parsed_date,
                connection_status=pending_status,
                follow_up_message=None,
                user=user,
            )
            created_count += 1

        if created_count:
            success_message = f"Imported {created_count} sent connections (status defaulted to Pending)."
            if created_message_type_count:
                success_message += f" Created {created_message_type_count} new message format(s)."
            messages.success(
                request,
                success_message,
            )

        if failed_rows:
            messages.warning(request, "Some rows failed: " + " | ".join(failed_rows[:5]))

        return redirect("sent_connections_list")

    return render(
        request,
        "tracker/upload_csv.html",
        {
            "form": form,
            "title": "Upload Sent Connections CSV",
            "sample_headers": "name,profile_link,message,message_format,date",
        },
    )


@login_required
def update_connection_status(request):
    results = SentConnection.objects.none()
    statuses = ConnectionStatus.objects.filter(
        Q(name__iexact="Pending") | Q(name__iexact="Accepted") | Q(name__iexact="Rejected")
    )

    if request.method == "POST" and request.POST.get("connection_id"):
        connection_id = request.POST.get("connection_id")
        status_id = request.POST.get("status_id")
        status_date = parse_filter_date(request.POST.get("status_date")) or timezone.localdate()

        connection = get_object_or_404(SentConnection, pk=connection_id)
        status = get_object_or_404(ConnectionStatus, pk=status_id)
        connection.connection_status = status
        connection.status_date = status_date

        update_fields = ["connection_status", "status_date", "updated_at"]
        follow_up_message = (
            FollowUpMessage.objects.filter(user=connection.user, message_id=connection.message_id).first()
            if status.name.lower() == "accepted"
            else None
        )
        if follow_up_message:
            apply_follow_up_template_to_connection(connection, follow_up_message, save=False)
            update_fields.extend(["follow_up_message", "follow_up_message_1", "follow_up_message_2", "follow_up_message_3"])

        connection.save(update_fields=list(dict.fromkeys(update_fields)))

        status_message = f"Status updated to {status.name} for {connection.name}."
        if status.name.lower() == "accepted" and follow_up_message:
            status_message += " Follow up messages were generated automatically."
        elif status.name.lower() == "accepted":
            status_message += " No follow up template was found for this Message ID."
        messages.success(request, status_message)

        params = {}
        user_id = request.POST.get("current_user", "")
        query = request.POST.get("current_query", "")
        if user_id:
            params["user"] = user_id
        if query:
            params["name"] = query

        redirect_url = reverse("update_connection_status")
        if params:
            redirect_url += f"?{urlencode(params)}"
        return HttpResponseRedirect(redirect_url)

    search_form = StatusSearchForm(request.GET or None)
    if search_form.is_valid():
        user = search_form.cleaned_data["user"]
        name = search_form.cleaned_data["name"]
        results = SentConnection.objects.filter(
            user=user,
            name__icontains=name,
        ).select_related("connection_status", "user")

    return render(
        request,
        "tracker/update_connection_status.html",
        {
            "search_form": search_form,
            "results": results,
            "statuses": statuses,
            "today": timezone.localdate().isoformat(),
        },
    )


@login_required
def follow_up_hub(request):
    users = list(User.objects.filter(is_active=True).order_by("username"))
    selected_user_id = request.GET.get("user", "").strip()
    search_query = request.GET.get("search", "").strip()
    selected_follow_up_count = request.GET.get("follow_up_sent_count", "").strip()
    from_date = parse_filter_date(request.GET.get("from_date", ""))
    to_date = parse_filter_date(request.GET.get("to_date", ""))
    if from_date and to_date and from_date > to_date:
        from_date, to_date = to_date, from_date

    if not selected_user_id and users:
        selected_user_id = str(users[0].id)

    def redirect_with_filters(params_override=None):
        params = {
            "user": request.POST.get("current_user", selected_user_id),
            "search": request.POST.get("current_search", search_query),
            "follow_up_sent_count": request.POST.get("current_follow_up_sent_count", selected_follow_up_count),
            "from_date": request.POST.get("current_from_date", from_date.isoformat() if from_date else ""),
            "to_date": request.POST.get("current_to_date", to_date.isoformat() if to_date else ""),
        }
        if params_override:
            params.update(params_override)

        filtered_params = {key: value for key, value in params.items() if value}
        redirect_url = reverse("follow_up_hub")
        if filtered_params:
            redirect_url += f"?{urlencode(filtered_params)}"
        return HttpResponseRedirect(redirect_url)

    if request.method == "POST" and request.POST.get("action") == "mark_sent":
        connection = get_object_or_404(SentConnection, pk=request.POST.get("connection_id"))
        follow_up_index = request.POST.get("follow_up_index", "").strip()
        if follow_up_index not in {"1", "2", "3"}:
            messages.error(request, "Invalid follow up selection.")
            return redirect_with_filters()

        sent_date = parse_filter_date(request.POST.get("sent_date")) or timezone.localdate()
        field_name = f"follow_up_sent_date_{follow_up_index}"
        setattr(connection, field_name, sent_date)
        connection.save(update_fields=[field_name, "updated_at"])
        messages.success(request, f"Follow up {follow_up_index} marked as sent for {connection.name}.")
        return redirect_with_filters()

    if request.method == "POST" and request.POST.get("action") == "update_responded":
        connection = get_object_or_404(SentConnection, pk=request.POST.get("connection_id"))
        responded_value = request.POST.get("responded", "").strip().lower()
        if responded_value not in {"true", "false"}:
            messages.error(request, "Invalid responded value.")
            return redirect_with_filters()

        connection.responded = responded_value == "true"
        connection.save(update_fields=["responded", "updated_at"])
        messages.success(
            request,
            f"Responded updated to {'True' if connection.responded else 'False'} for {connection.name}.",
        )
        return redirect_with_filters()

    accepted_status = ConnectionStatus.objects.filter(name__iexact="Accepted").first()
    connections = (
        SentConnection.objects.select_related("user", "connection_status")
        .annotate(follow_up_sent_count=follow_up_sent_count_expression())
        .filter(connection_status=accepted_status)
        if accepted_status
        else SentConnection.objects.none()
    )

    if selected_user_id:
        connections = connections.filter(user_id=selected_user_id)

    if search_query:
        connections = connections.filter(
            Q(name__icontains=search_query)
            | Q(profile_link__icontains=search_query)
            | Q(message__icontains=search_query)
            | Q(message_id__icontains=search_query)
        )

    if selected_follow_up_count != "":
        try:
            follow_up_count_value = 0 if selected_follow_up_count == "none" else int(selected_follow_up_count)
            connections = connections.filter(follow_up_sent_count=follow_up_count_value)
        except ValueError:
            selected_follow_up_count = ""

    if from_date:
        connections = connections.filter(Q(status_date__gte=from_date) | (Q(status_date__isnull=True) & Q(date__gte=from_date)))
    if to_date:
        connections = connections.filter(Q(status_date__lte=to_date) | (Q(status_date__isnull=True) & Q(date__lte=to_date)))

    connections = connections.order_by("-status_date", "-date", "-id")

    if request.GET.get("download") == "1":
        response = HttpResponse(content_type="text/csv")
        filename = f"follow_ups_filtered_{timezone.localdate().isoformat()}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Name",
                "User",
                "Message ID",
                "Accepted Date",
                "Responded",
                "Follow Up Sent Count",
                "Follow Up 1",
                "Follow Up Sent Date 1",
                "Follow Up 2",
                "Follow Up Sent Date 2",
                "Follow Up 3",
                "Follow Up Sent Date 3",
            ]
        )
        for row in connections:
            writer.writerow(
                [
                    row.name,
                    row.user.username,
                    row.message_id,
                    row.status_date.isoformat() if row.status_date else (row.date.isoformat() if row.date else ""),
                    "True" if row.responded else "False",
                    row.follow_up_sent_count,
                    row.follow_up_message_1,
                    row.follow_up_sent_date_1.isoformat() if row.follow_up_sent_date_1 else "",
                    row.follow_up_message_2,
                    row.follow_up_sent_date_2.isoformat() if row.follow_up_sent_date_2 else "",
                    row.follow_up_message_3,
                    row.follow_up_sent_date_3.isoformat() if row.follow_up_sent_date_3 else "",
                ]
            )
        return response

    return render(
        request,
        "tracker/follow_up_hub.html",
        {
            "users": users,
            "connections": connections,
            "selected_user_id": selected_user_id,
            "selected_search_query": search_query,
            "selected_follow_up_count": selected_follow_up_count,
            "selected_from_date": from_date.isoformat() if from_date else "",
            "selected_to_date": to_date.isoformat() if to_date else "",
            "today": timezone.localdate().isoformat(),
        },
    )


@login_required
def user_list(request):
    users = User.objects.order_by("username")
    return render(request, "tracker/user_list.html", {"users": users})


@login_required
def user_create(request):
    form = TrackerUserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User created.")
        return redirect("user_list")
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": "Add User", "cancel_url": reverse("user_list")},
    )


@login_required
def user_detail(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    return render(request, "tracker/user_detail.html", {"user_obj": user_obj})


@login_required
def user_edit(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    form = TrackerUserUpdateForm(request.POST or None, instance=user_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User updated.")
        return redirect("user_list")
    return render(
        request,
        "tracker/form_page.html",
        {"form": form, "title": "Edit User", "cancel_url": reverse("user_list")},
    )


@login_required
def user_deactivate(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        user_obj.is_active = False
        user_obj.save(update_fields=["is_active"])
        messages.success(request, f"User '{user_obj.username}' marked inactive.")
        return redirect("user_list")
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "title": "Mark User Inactive",
            "object_name": user_obj.username,
            "cancel_url": reverse("user_list"),
        },
    )
