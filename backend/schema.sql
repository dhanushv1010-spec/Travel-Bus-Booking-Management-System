SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS waitlist;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS trips;
DROP TABLE IF EXISTS buses;
DROP TABLE IF EXISTS routes;
DROP TABLE IF EXISTS cities;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS=1;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  username VARCHAR(40) NOT NULL UNIQUE,
  email VARCHAR(120),
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin','customer','manager') NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cities (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(60) NOT NULL UNIQUE
);

CREATE TABLE routes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  city_a INT NOT NULL,
  city_b INT NOT NULL,
  distance_km INT NOT NULL,
  UNIQUE KEY uq_route (city_a, city_b),
  FOREIGN KEY (city_a) REFERENCES cities(id),
  FOREIGN KEY (city_b) REFERENCES cities(id)
);

CREATE TABLE buses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  reg_no VARCHAR(20) NOT NULL UNIQUE,
  name VARCHAR(60) NOT NULL,
  total_seats INT NOT NULL DEFAULT 40,
  rate_per_km DECIMAL(6,2) NOT NULL DEFAULT 2.00,
  manager_id INT NULL,
  FOREIGN KEY (manager_id) REFERENCES users(id)
);

CREATE TABLE trips (
  id INT AUTO_INCREMENT PRIMARY KEY,
  bus_id INT NOT NULL,
  route_id INT NOT NULL,
  source_id INT NOT NULL,
  dest_id INT NOT NULL,
  travel_date DATE NOT NULL,
  departure_time TIME NOT NULL,
  status ENUM('SCHEDULED','CANCELLED') NOT NULL DEFAULT 'SCHEDULED',
  INDEX idx_search (source_id, dest_id, travel_date),
  FOREIGN KEY (bus_id) REFERENCES buses(id),
  FOREIGN KEY (route_id) REFERENCES routes(id),
  FOREIGN KEY (source_id) REFERENCES cities(id),
  FOREIGN KEY (dest_id) REFERENCES cities(id)
);

CREATE TABLE bookings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  pnr VARCHAR(12) NOT NULL UNIQUE,
  group_ref VARCHAR(12) NOT NULL,
  trip_id INT NOT NULL,
  user_id INT NOT NULL,
  passenger_name VARCHAR(60) NOT NULL,
  age INT NOT NULL,
  seat_no INT NOT NULL,
  seat_class ENUM('Economy','Premium','Deluxe') NOT NULL,
  fare DECIMAL(10,2) NOT NULL,
  refund DECIMAL(10,2) NOT NULL DEFAULT 0,
  status ENUM('CONFIRMED','CANCELLED') NOT NULL DEFAULT 'CONFIRMED',
  active TINYINT NULL,
  booked_at DATETIME NOT NULL,
  cancelled_at DATETIME NULL,
  UNIQUE KEY uq_seat (trip_id, seat_no, active),
  INDEX idx_user (user_id),
  FOREIGN KEY (trip_id) REFERENCES trips(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE waitlist (
  id INT AUTO_INCREMENT PRIMARY KEY,
  trip_id INT NOT NULL,
  user_id INT NOT NULL,
  seats_needed INT NOT NULL,
  seat_class ENUM('Economy','Premium','Deluxe') NOT NULL,
  preference VARCHAR(10) NOT NULL DEFAULT 'any',
  passengers TEXT NOT NULL,
  status ENUM('WAITING','PROMOTED','CANCELLED') NOT NULL DEFAULT 'WAITING',
  created_at DATETIME NOT NULL,
  INDEX idx_wait (trip_id, status),
  FOREIGN KEY (trip_id) REFERENCES trips(id),
  FOREIGN KEY (user_id) REFERENCES users(id)
);
