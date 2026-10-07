-- Run after sql/019_multi_venue_tentative_holds.sql has committed.
-- Every tentative hold must carry the deadline that releases the venue.
alter table venue_bookings
    add constraint ck_venue_booking_hold_requires_expiry
    check (status <> 'tentative_hold' or expires_at is not null);
