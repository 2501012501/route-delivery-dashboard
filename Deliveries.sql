-- Bring only the last 7 days of deliveries to speed up the load.
DECLARE @StartDate VARCHAR(10) = CONVERT(VARCHAR(10), DATEADD(DAY, -7, GETDATE()), 111)
DECLARE @EndDate   VARCHAR(10) = CONVERT(VARCHAR(10), GETDATE(), 111)

EXEC dbo.Exstconsultacustomerinventario @StartDate, @EndDate, 0, 0