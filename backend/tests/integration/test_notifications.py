import uuid

from app.models.notification import Notification, NotificationDelivery
from app.services.notification_service import NotificationService
from app.utils.enums import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationStatus,
    UserRole,
)
from tests.helpers import authenticate_client


def create_notification(
    db_session,
    *,
    user_id,
    title: str = "Test notification",
    message: str = "This is a test notification.",
    event_type: NotificationEventType = NotificationEventType.TASK_ASSIGNED,
    resource_type: str | None = "task",
    resource_id=None,
    channels=(NotificationChannel.IN_APP,),
):
    service = NotificationService(db_session)

    return service.create_notification(
        user_id=user_id,
        title=title,
        message=message,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        channels=channels,
    )


def test_notification_can_be_created(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-create-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    resource_id = uuid.uuid4()

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="New task assigned",
        message="A new task has been assigned to you.",
        event_type=NotificationEventType.TASK_ASSIGNED,
        resource_type="task",
        resource_id=resource_id,
    )

    assert notification.id is not None
    assert notification.user_id == user.id
    assert notification.title == "New task assigned"
    assert notification.message == "A new task has been assigned to you."
    assert notification.status == NotificationStatus.UNREAD
    assert notification.event_type == NotificationEventType.TASK_ASSIGNED.value
    assert notification.resource_type == "task"
    assert notification.resource_id == resource_id

    deliveries = (
        db_session.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification.id,
        )
        .all()
    )

    assert len(deliveries) == 1
    assert deliveries[0].channel == NotificationChannel.IN_APP
    assert deliveries[0].status == NotificationDeliveryStatus.DELIVERED
    assert deliveries[0].delivered_at is not None


def test_notification_title_and_message_are_trimmed(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-trim-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="  Test notification  ",
        message="  Notification message.  ",
    )

    assert notification.title == "Test notification"
    assert notification.message == "Notification message."


def test_notification_can_be_created_for_multiple_channels(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-channels-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        channels=(
            NotificationChannel.IN_APP,
            NotificationChannel.EMAIL,
        ),
    )

    deliveries = (
        db_session.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification.id,
        )
        .order_by(NotificationDelivery.channel.asc())
        .all()
    )

    assert len(deliveries) == 2

    delivery_by_channel = {delivery.channel: delivery for delivery in deliveries}

    assert (
        delivery_by_channel[NotificationChannel.IN_APP].status
        == NotificationDeliveryStatus.DELIVERED
    )

    assert delivery_by_channel[NotificationChannel.IN_APP].delivered_at is not None

    assert (
        delivery_by_channel[NotificationChannel.EMAIL].status
        == NotificationDeliveryStatus.PENDING
    )

    assert delivery_by_channel[NotificationChannel.EMAIL].delivered_at is None


def test_duplicate_notification_channels_create_one_delivery_per_channel(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-duplicate-channel-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        channels=(
            NotificationChannel.IN_APP,
            NotificationChannel.IN_APP,
        ),
    )

    deliveries = (
        db_session.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification.id,
        )
        .all()
    )

    assert len(deliveries) == 1
    assert deliveries[0].channel == NotificationChannel.IN_APP


def test_notification_cannot_be_created_for_nonexistent_user(
    db_session,
    cleanup_notifications,
):
    service = NotificationService(db_session)

    nonexistent_user_id = uuid.uuid4()

    try:
        service.create_notification(
            user_id=nonexistent_user_id,
            title="Test notification",
            message="Test message.",
            event_type=NotificationEventType.TASK_ASSIGNED,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError(
            "Creating a notification for a nonexistent user should fail.",
        )


def test_notification_cannot_be_created_for_deleted_user(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-deleted-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    user.is_deleted = True
    db_session.add(user)
    db_session.commit()

    service = NotificationService(db_session)

    try:
        service.create_notification(
            user_id=user.id,
            title="Test notification",
            message="Test message.",
            event_type=NotificationEventType.TASK_ASSIGNED,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError(
            "Creating a notification for a deleted user should fail.",
        )


def test_notification_requires_title(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-no-title-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    service = NotificationService(db_session)

    try:
        service.create_notification(
            user_id=user.id,
            title="   ",
            message="Test message.",
            event_type=NotificationEventType.TASK_ASSIGNED,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError(
            "Creating a notification without a title should fail.",
        )


def test_notification_requires_message(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-no-message-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    service = NotificationService(db_session)

    try:
        service.create_notification(
            user_id=user.id,
            title="Test notification",
            message="   ",
            event_type=NotificationEventType.TASK_ASSIGNED,
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError(
            "Creating a notification without a message should fail.",
        )


def test_user_can_list_their_notifications(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-list-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    first = create_notification(
        db_session,
        user_id=user.id,
        title="First notification",
        message="First message.",
        resource_id=uuid.uuid4(),
    )

    second = create_notification(
        db_session,
        user_id=user.id,
        title="Second notification",
        message="Second message.",
        resource_id=uuid.uuid4(),
    )

    db_session.commit()

    authenticate_client(client, user)

    response = client.get(
        "/api/v1/notifications",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 1

    notification_ids = {notification["id"] for notification in data["notifications"]}

    assert str(first.id) in notification_ids
    assert str(second.id) in notification_ids


def test_user_cannot_see_another_users_notifications(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    first_user = create_test_user(
        email=f"notification-owner-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    second_user = create_test_user(
        email=f"notification-other-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=first_user.id,
        title="Private notification",
        message="This belongs to another user.",
        resource_id=uuid.uuid4(),
    )

    db_session.commit()

    authenticate_client(client, second_user)

    response = client.get(
        "/api/v1/notifications",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    notification_ids = {item["id"] for item in data["notifications"]}

    assert str(notification.id) not in notification_ids


def test_user_can_get_one_notification(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-get-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="Notification details",
        message="Detailed notification message.",
        resource_type="task",
        resource_id=uuid.uuid4(),
    )

    db_session.commit()

    authenticate_client(client, user)

    response = client.get(
        f"/api/v1/notifications/{notification.id}",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == str(notification.id)
    assert data["user_id"] == str(user.id)
    assert data["title"] == "Notification details"
    assert data["message"] == "Detailed notification message."
    assert data["status"] == NotificationStatus.UNREAD.value
    assert data["event_type"] == NotificationEventType.TASK_ASSIGNED.value
    assert data["resource_type"] == "task"
    assert data["resource_id"] == str(notification.resource_id)
    assert data["read_at"] is None

    assert len(data["deliveries"]) == 1
    assert data["deliveries"][0]["channel"] == NotificationChannel.IN_APP.value
    assert data["deliveries"][0]["status"] == NotificationDeliveryStatus.DELIVERED.value


def test_user_cannot_get_another_users_notification(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    owner = create_test_user(
        email=f"notification-get-owner-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    other_user = create_test_user(
        email=f"notification-get-other-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=owner.id,
        title="Private notification",
        message="Private message.",
    )

    db_session.commit()

    authenticate_client(client, other_user)

    response = client.get(
        f"/api/v1/notifications/{notification.id}",
    )

    assert response.status_code == 404


def test_unread_notification_count_is_correct(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-count-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    first = create_notification(
        db_session,
        user_id=user.id,
        title="Unread one",
        message="Message one.",
    )

    create_notification(
        db_session,
        user_id=user.id,
        title="Unread two",
        message="Message two.",
    )

    db_session.commit()

    authenticate_client(client, user)

    response = client.get(
        "/api/v1/notifications/unread-count",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["unread_count"] == 2

    db_session.refresh(first)


def test_user_can_filter_notifications_by_unread_status(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-filter-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    unread_notification = create_notification(
        db_session,
        user_id=user.id,
        title="Unread notification",
        message="Unread message.",
    )

    read_notification = create_notification(
        db_session,
        user_id=user.id,
        title="Read notification",
        message="Read message.",
    )

    db_session.commit()

    service = NotificationService(db_session)

    service.mark_as_read(
        notification_id=read_notification.id,
        user_id=user.id,
    )

    authenticate_client(client, user)

    response = client.get(
        "/api/v1/notifications",
        params={
            "status": NotificationStatus.UNREAD.value,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    notification_ids = {item["id"] for item in data["notifications"]}

    assert str(unread_notification.id) in notification_ids
    assert str(read_notification.id) not in notification_ids


def test_notification_can_be_marked_as_read(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-read-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="Read this notification",
        message="This notification should become read.",
    )

    db_session.commit()

    assert notification.status == NotificationStatus.UNREAD
    assert notification.read_at is None

    authenticate_client(client, user)

    response = client.patch(
        f"/api/v1/notifications/{notification.id}/read",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == str(notification.id)
    assert data["status"] == NotificationStatus.READ.value
    assert data["read_at"] is not None


def test_marking_notification_as_read_is_idempotent(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-idempotent-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="Idempotent notification",
        message="This notification will be read twice.",
    )

    db_session.commit()

    authenticate_client(client, user)

    first_response = client.patch(
        f"/api/v1/notifications/{notification.id}/read",
    )

    assert first_response.status_code == 200

    first_data = first_response.json()["data"]

    first_read_at = first_data["read_at"]

    second_response = client.patch(
        f"/api/v1/notifications/{notification.id}/read",
    )

    assert second_response.status_code == 200

    second_data = second_response.json()["data"]

    assert second_data["status"] == NotificationStatus.READ.value
    assert second_data["read_at"] == first_read_at


def test_marking_another_users_notification_as_read_returns_404(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    owner = create_test_user(
        email=f"notification-read-owner-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    other_user = create_test_user(
        email=f"notification-read-other-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=owner.id,
        title="Private notification",
        message="Private message.",
    )

    db_session.commit()

    authenticate_client(client, other_user)

    response = client.patch(
        f"/api/v1/notifications/{notification.id}/read",
    )

    assert response.status_code == 404


def test_notification_delivery_can_be_marked_delivered(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-delivered-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="Email notification",
        message="This notification uses email.",
        channels=(NotificationChannel.EMAIL,),
    )

    delivery = (
        db_session.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification.id,
            NotificationDelivery.channel == NotificationChannel.EMAIL,
        )
        .first()
    )

    assert delivery is not None
    assert delivery.status == NotificationDeliveryStatus.PENDING
    assert delivery.delivered_at is None

    service = NotificationService(db_session)

    updated_delivery = service.update_delivery_status(
        delivery_id=delivery.id,
        status=NotificationDeliveryStatus.DELIVERED,
    )

    assert updated_delivery.status == NotificationDeliveryStatus.DELIVERED
    assert updated_delivery.delivered_at is not None
    assert updated_delivery.failure_reason is None


def test_notification_delivery_can_be_marked_failed(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-failed-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="Email notification",
        message="This notification should fail.",
        channels=(NotificationChannel.EMAIL,),
    )

    delivery = (
        db_session.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification.id,
            NotificationDelivery.channel == NotificationChannel.EMAIL,
        )
        .first()
    )

    assert delivery is not None

    service = NotificationService(db_session)

    updated_delivery = service.update_delivery_status(
        delivery_id=delivery.id,
        status=NotificationDeliveryStatus.FAILED,
        failure_reason="SMTP connection failed.",
    )

    assert updated_delivery.status == NotificationDeliveryStatus.FAILED
    assert updated_delivery.failure_reason == "SMTP connection failed."
    assert updated_delivery.delivered_at is None


def test_notification_delivery_failure_uses_default_reason(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-default-failure-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="Email notification",
        message="This notification should fail.",
        channels=(NotificationChannel.EMAIL,),
    )

    delivery = (
        db_session.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification.id,
        )
        .first()
    )

    assert delivery is not None

    service = NotificationService(db_session)

    updated_delivery = service.update_delivery_status(
        delivery_id=delivery.id,
        status=NotificationDeliveryStatus.FAILED,
    )

    assert updated_delivery.failure_reason == "Notification delivery failed."


def test_notification_delivery_can_return_to_pending(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-pending-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
        title="Email notification",
        message="This notification can be retried.",
        channels=(NotificationChannel.EMAIL,),
    )

    delivery = (
        db_session.query(NotificationDelivery)
        .filter(
            NotificationDelivery.notification_id == notification.id,
        )
        .first()
    )

    assert delivery is not None

    service = NotificationService(db_session)

    service.update_delivery_status(
        delivery_id=delivery.id,
        status=NotificationDeliveryStatus.FAILED,
        failure_reason="Temporary failure.",
    )

    updated_delivery = service.update_delivery_status(
        delivery_id=delivery.id,
        status=NotificationDeliveryStatus.PENDING,
    )

    assert updated_delivery.status == NotificationDeliveryStatus.PENDING
    assert updated_delivery.failure_reason is None


def test_notification_list_pagination(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-pagination-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    for index in range(25):
        create_notification(
            db_session,
            user_id=user.id,
            title=f"Notification {index}",
            message=f"Notification message {index}.",
        )

    db_session.commit()

    authenticate_client(client, user)

    first_response = client.get(
        "/api/v1/notifications",
        params={
            "page": 1,
            "page_size": 10,
        },
    )

    assert first_response.status_code == 200

    first_data = first_response.json()["data"]

    assert first_data["total"] == 25
    assert first_data["page"] == 1
    assert first_data["page_size"] == 10
    assert first_data["total_pages"] == 3
    assert len(first_data["notifications"]) == 10

    third_response = client.get(
        "/api/v1/notifications",
        params={
            "page": 3,
            "page_size": 10,
        },
    )

    assert third_response.status_code == 200

    third_data = third_response.json()["data"]

    assert len(third_data["notifications"]) == 5


def test_notification_list_can_be_paginated_beyond_first_page(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-pagination-second-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    for index in range(3):
        create_notification(
            db_session,
            user_id=user.id,
            title=f"Notification {index}",
            message=f"Message {index}.",
        )

    db_session.commit()

    authenticate_client(client, user)

    response = client.get(
        "/api/v1/notifications",
        params={
            "page": 2,
            "page_size": 2,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["total"] == 3
    assert data["page"] == 2
    assert data["page_size"] == 2
    assert data["total_pages"] == 2
    assert len(data["notifications"]) == 1


def test_auditor_can_view_notifications(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    auditor = create_test_user(
        email=f"notification-auditor-{uuid.uuid4()}@example.com",
        role=UserRole.AUDITOR,
    )

    create_notification(
        db_session,
        user_id=auditor.id,
        title="Audit notification",
        message="Auditor notification.",
    )

    db_session.commit()

    authenticate_client(client, auditor)

    response = client.get(
        "/api/v1/notifications",
    )

    assert response.status_code == 200


def test_auditor_can_view_own_notifications(
    client,
    db_session,
    create_test_user,
    cleanup_notifications,
):
    auditor = create_test_user(
        email=f"notification-auditor-{uuid.uuid4()}@example.com",
        role=UserRole.AUDITOR,
    )

    notification = create_notification(
        db_session,
        user_id=auditor.id,
        title="Audit notification",
        message="Auditor notification.",
    )

    db_session.commit()

    authenticate_client(client, auditor)

    response = client.get(
        f"/api/v1/notifications/{notification.id}",
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == str(notification.id)
    assert data["user_id"] == str(auditor.id)


def test_notification_status_is_persisted(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-persisted-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
    )

    db_session.commit()
    db_session.expire_all()

    saved_notification = (
        db_session.query(Notification)
        .filter(
            Notification.id == notification.id,
        )
        .first()
    )

    assert saved_notification is not None
    assert saved_notification.status == NotificationStatus.UNREAD
    assert saved_notification.read_at is None


def test_read_notification_is_persisted(
    db_session,
    create_test_user,
    cleanup_notifications,
):
    user = create_test_user(
        email=f"notification-read-persisted-{uuid.uuid4()}@example.com",
        role=UserRole.REVIEWER,
    )

    notification = create_notification(
        db_session,
        user_id=user.id,
    )

    db_session.commit()

    service = NotificationService(db_session)

    service.mark_as_read(
        notification_id=notification.id,
        user_id=user.id,
    )

    db_session.expire_all()

    saved_notification = (
        db_session.query(Notification)
        .filter(
            Notification.id == notification.id,
        )
        .first()
    )

    assert saved_notification is not None
    assert saved_notification.status == NotificationStatus.READ
    assert saved_notification.read_at is not None
