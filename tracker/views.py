import csv
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from .forms import (
    CSVUploadForm,
    MessageTypeCreateForm,
    MessageTypeForm,
    StatusSearchForm,
    TrackerUserCreateForm,
    TrackerUserUpdateForm,
    UserFilterForm,
)
from .models import ConnectionStatus, MessageType, SentConnection

User = get_user_model()


@login_required
def dashboard(request):
    users = list(User.objects.filter(is_active=True).order_by("username"))
    selected_user = None

    selected_user_id = request.GET.get("user", "")
    if selected_user_id:
        selected_user = next((u for u in users if str(u.id) == selected_user_id), None)

    if selected_user is None and users:
        selected_user = users[0]

    def parse_filter_date(raw_value):
        value = (raw_value or "").strip()
        if not value:
            return None
        parsed = parse_date(value)
        if parsed:
            return parsed
        for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%m-%d-%Y"):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue
        return None

    from_date_raw = request.GET.get("from_date", "").strip()
    to_date_raw = request.GET.get("to_date", "").strip()
    from_date = parse_filter_date(from_date_raw)
    to_date = parse_filter_date(to_date_raw)
    if from_date and to_date and from_date > to_date:
        from_date, to_date = to_date, from_date
    has_date_filter = bool(from_date or to_date)

    def apply_date_range(queryset):
        if from_date:
            queryset = queryset.filter(date__gte=from_date)
        if to_date:
            queryset = queryset.filter(date__lte=to_date)
        return queryset

    message_ids = []
    message_options = []
    selected_message_label = "All Message IDs"
    selected_message_id = request.GET.get("message_id", "").strip()
    user_connections = SentConnection.objects.none()
    selected_connections = SentConnection.objects.none()
    selected_connections_for_date = SentConnection.objects.none()

    if selected_user:
        user_connections = SentConnection.objects.filter(user=selected_user)
        selected_connections = user_connections
        message_ids = [
            item["message_id"]
            for item in user_connections.exclude(message_id="")
            .values("message_id")
            .distinct()
            .order_by("message_id")
        ]
        message_type_map = {
            row["message_id"]: row["message"]
            for row in MessageType.objects.filter(user=selected_user, message_id__in=message_ids).values(
                "message_id", "message"
            )
        }
        connection_message_map = {}
        for message_id, message in (
            user_connections.exclude(message_id="")
            .exclude(message="")
            .values_list("message_id", "message")
            .order_by("message_id", "id")
        ):
            if message_id not in connection_message_map:
                connection_message_map[message_id] = message

        for message_id in message_ids:
            raw_message = message_type_map.get(message_id) or connection_message_map.get(message_id) or ""
            one_line_message = " ".join(raw_message.split())
            preview = one_line_message[:80] + ("..." if len(one_line_message) > 80 else "")
            message_options.append(
                {
                    "message_id": message_id,
                    "message_text": one_line_message,
                    "message_preview": preview,
                }
            )

        if selected_message_id and selected_message_id in message_ids:
            selected_connections = selected_connections.filter(message_id=selected_message_id)
            for option in message_options:
                if option["message_id"] == selected_message_id:
                    selected_message_label = option["message_id"]
                    if option["message_preview"]:
                        selected_message_label += f" - {option['message_preview']}"
                    break
        else:
            selected_message_id = ""
        selected_connections_for_date = apply_date_range(selected_connections)

    today = timezone.localdate()
    reference_end = today
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    accepted_status = ConnectionStatus.objects.filter(name__iexact="Accepted").first()
    pending_status = ConnectionStatus.objects.filter(name__iexact="Pending").first()
    follow_up_sent_filter = (
        Q(follow_up_message__isnull=False)
        | Q(follow_up_message_1__gt="")
        | Q(follow_up_message_2__gt="")
        | Q(follow_up_message_3__gt="")
    )

    def period_counts(queryset):
        return {
            "week": queryset.filter(date__gte=week_start, date__lte=reference_end).count(),
            "month": queryset.filter(date__gte=month_start, date__lte=reference_end).count(),
            "total": queryset.count(),
        }

    def date_filter_count(queryset):
        return apply_date_range(queryset).count() if has_date_filter else queryset.count()

    sent_counts = period_counts(selected_connections)
    filtered_sent_count = selected_connections_for_date.count() if has_date_filter else selected_connections.count()
    global_sent_counts = period_counts(user_connections)

    accepted_selected_connections = (
        selected_connections.filter(connection_status=accepted_status)
        if accepted_status
        else selected_connections.none()
    )
    accepted_counts = period_counts(
        accepted_selected_connections
    )
    filtered_accepted_count = date_filter_count(accepted_selected_connections)

    accepted_user_connections = (
        user_connections.filter(connection_status=accepted_status)
        if accepted_status
        else user_connections.none()
    )
    global_accepted_counts = period_counts(accepted_user_connections)

    pending_selected_connections = (
        selected_connections.filter(connection_status=pending_status)
        if pending_status
        else selected_connections.none()
    )
    pending_counts = period_counts(
        pending_selected_connections
    )
    filtered_pending_count = date_filter_count(pending_selected_connections)

    follow_up_selected_connections = selected_connections.filter(follow_up_sent_filter)
    follow_up_counts = period_counts(follow_up_selected_connections)
    filtered_follow_up_count = date_filter_count(follow_up_selected_connections)

    follow_up_user_connections = user_connections.filter(follow_up_sent_filter)
    global_follow_up_counts = period_counts(follow_up_user_connections)

    if has_date_filter:
        date_filter_label = "Date Filter"
    else:
        date_filter_label = "Date Filter (Overall)"

    return render(
        request,
        "tracker/dashboard.html",
        {
            "users": users,
            "selected_user": selected_user,
            "message_ids": message_ids,
            "message_options": message_options,
            "selected_message_id": selected_message_id,
            "selected_message_label": selected_message_label,
            "from_date": from_date.isoformat() if from_date else "",
            "to_date": to_date.isoformat() if to_date else "",
            "sent_counts": sent_counts,
            "filtered_sent_count": filtered_sent_count,
            "global_sent_counts": global_sent_counts,
            "accepted_counts": accepted_counts,
            "filtered_accepted_count": filtered_accepted_count,
            "global_accepted_counts": global_accepted_counts,
            "pending_counts": pending_counts,
            "filtered_pending_count": filtered_pending_count,
            "follow_up_counts": follow_up_counts,
            "filtered_follow_up_count": filtered_follow_up_count,
            "global_follow_up_counts": global_follow_up_counts,
            "has_date_filter": has_date_filter,
            "date_filter_label": date_filter_label,
        },
    )


@login_required
def sent_connections_list(request):
    users = User.objects.filter(is_active=True).order_by("username")
    selected_user_id = request.GET.get("user", "").strip()
    selected_message_id = request.GET.get("message_id", "").strip()
    selected_status_id = request.GET.get("status", "").strip()
    selected_follow_up_count = request.GET.get("follow_up_sent_count", "").strip()
    from_date_raw = request.GET.get("from_date", "").strip()
    to_date_raw = request.GET.get("to_date", "").strip()
    from_date = parse_date(from_date_raw) if from_date_raw else None
    to_date = parse_date(to_date_raw) if to_date_raw else None
    if from_date and to_date and from_date > to_date:
        from_date, to_date = to_date, from_date

    follow_up_count_expr = (
        Case(When(follow_up_message_1__gt="", then=Value(1)), default=Value(0), output_field=IntegerField())
        + Case(When(follow_up_message_2__gt="", then=Value(1)), default=Value(0), output_field=IntegerField())
        + Case(When(follow_up_message_3__gt="", then=Value(1)), default=Value(0), output_field=IntegerField())
    )

    connections = (
        SentConnection.objects.select_related("user", "connection_status")
        .annotate(follow_up_sent_count=follow_up_count_expr)
    )

    if selected_user_id:
        connections = connections.filter(user_id=selected_user_id)

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

    if from_date:
        connections = connections.filter(date__gte=from_date)
    if to_date:
        connections = connections.filter(date__lte=to_date)

    message_ids_queryset = SentConnection.objects.exclude(message_id="")
    if selected_user_id:
        message_ids_queryset = message_ids_queryset.filter(user_id=selected_user_id)
    message_id_options = (
        message_ids_queryset.values_list("message_id", flat=True).distinct().order_by("message_id")
    )

    status_options = ConnectionStatus.objects.order_by("id")

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
                "Status",
                "Follow Up Sent Count",
                "Follow Up 1",
                "Follow Up 2",
                "Follow Up 3",
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
                    row.connection_status.name if row.connection_status else "",
                    row.follow_up_sent_count,
                    row.follow_up_message_1,
                    row.follow_up_message_2,
                    row.follow_up_message_3,
                    row.user.username if row.user else "",
                ]
            )

        return response

    context = {
        "connections": connections,
        "users": users,
        "message_id_options": message_id_options,
        "status_options": status_options,
        "selected_user_id": selected_user_id,
        "selected_message_id": selected_message_id,
        "selected_status_id": selected_status_id,
        "selected_follow_up_count": selected_follow_up_count,
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
    form = MessageTypeForm(request.POST or None, instance=message_type)
    if request.method == "POST" and form.is_valid():
        form.save()
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
    results = SentConnection.objects.none()

    if request.method == "POST" and request.POST.get("connection_id"):
        connection = get_object_or_404(SentConnection, pk=request.POST.get("connection_id"))
        connection.follow_up_message_1 = request.POST.get("follow_up_message_1", "").strip()
        connection.follow_up_message_2 = request.POST.get("follow_up_message_2", "").strip()
        connection.follow_up_message_3 = request.POST.get("follow_up_message_3", "").strip()
        connection.save(
            update_fields=[
                "follow_up_message_1",
                "follow_up_message_2",
                "follow_up_message_3",
                "updated_at",
            ]
        )
        messages.success(request, f"Follow up messages updated for {connection.name}.")

        params = {}
        current_user = request.POST.get("current_user", "")
        current_query = request.POST.get("current_query", "")
        if current_user:
            params["user"] = current_user
        if current_query:
            params["name"] = current_query

        redirect_url = reverse("follow_up_message_list")
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
        "tracker/follow_up_message_list.html",
        {
            "search_form": search_form,
            "results": results,
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


def _pick_follow_up_message(normalized_row, index):
    key_options = [
        f"follow_up_message_{index}",
        f"follow_up_message{index}",
    ]
    for key in key_options:
        if key in normalized_row:
            return normalized_row[key]
    return ""


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
            "message_id",
            "date",
            "follow_up_message_1",
            "follow_up_message_2",
            "follow_up_message_3",
        ]
    )
    writer.writerow(
        [
            "John Doe",
            "https://www.linkedin.com/in/john-doe",
            "Hi John, I'd like to connect.",
            "MSG001",
            "2026-02-27",
            "Following up on my connection request.",
            "Second reminder to connect.",
            "Final follow up message.",
        ]
    )
    return response


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

        required_columns = {"name", "profile_link", "message", "message_id", "date"}
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
                "CSV must contain headers: name, profile_link, message, message_id, date.",
            )
            return redirect("upload_sent_connections_csv")

        pending_status = ConnectionStatus.objects.filter(name__iexact="Pending").first()
        if pending_status is None:
            pending_status = ConnectionStatus.objects.create(name="Pending")

        created_count = 0
        failed_rows = []

        for line_number, row in enumerate(reader, start=2):
            normalized = {
                k.strip().lower().replace(" ", "_"): (v or "").strip()
                for k, v in row.items()
                if k
            }
            name = normalized.get("name", "")
            raw_date = normalized.get("date", "")

            if not name:
                failed_rows.append(f"Row {line_number}: name is required")
                continue

            parsed_date = _parse_csv_date(raw_date)
            if not parsed_date:
                failed_rows.append(f"Row {line_number}: invalid date '{raw_date}'")
                continue

            SentConnection.objects.create(
                name=name,
                profile_link=normalized.get("profile_link", ""),
                message=normalized.get("message", ""),
                message_id=normalized.get("message_id", ""),
                date=parsed_date,
                connection_status=pending_status,
                follow_up_message=None,
                follow_up_message_1=_pick_follow_up_message(normalized, 1),
                follow_up_message_2=_pick_follow_up_message(normalized, 2),
                follow_up_message_3=_pick_follow_up_message(normalized, 3),
                user=user,
            )
            created_count += 1

        if created_count:
            messages.success(
                request,
                f"Imported {created_count} sent connections (status defaulted to Pending).",
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
            "sample_headers": "name,profile_link,message,message_id,date (+ optional follow_up_message_1, follow_up_message_2, follow_up_message_3)",
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

        connection = get_object_or_404(SentConnection, pk=connection_id)
        status = get_object_or_404(ConnectionStatus, pk=status_id)
        connection.connection_status = status
        connection.save(update_fields=["connection_status", "updated_at"])
        messages.success(request, f"Status updated to {status.name} for {connection.name}.")

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
