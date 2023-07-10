CREATE TABLE stock(
	id serial PRIMARY KEY UNIQUE,
	user_id integer NOT NULL,
	stock_name varchar NOT NULL,
	averages varchar);
	
SELECT * FROM stock;