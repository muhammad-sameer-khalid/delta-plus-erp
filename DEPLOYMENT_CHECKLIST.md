# Deployment Checklist

## Pre-Deployment

- [ ] MySQL 8.0+ installed
- [ ] Python 3.8+ installed
- [ ] Database `delta_plus_erp` created
- [ ] `.env` file configured with correct credentials
- [ ] Virtual environment created
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Test setup passed (`python test_setup.py`)

## First Run

- [ ] Run `python app.py`
- [ ] Access http://localhost:5000
- [ ] Login with admin credentials (khalid.p38@gmail.com / admin123)
- [ ] Verify database tables created automatically
- [ ] Check admin panel accessible

## User Setup

- [ ] Create test users for each role
- [ ] Assign roles via admin panel
- [ ] Test role-based access restrictions
- [ ] Verify each user can access their modules

## Module Testing

### RND Module
- [ ] Create a test BOM
- [ ] Add multiple components
- [ ] View BOM list
- [ ] View BOM details
- [ ] Delete test BOM

### Production Module
- [ ] Create demand note
- [ ] Test approval workflow (Production → GM → Director)
- [ ] Send test product to QC
- [ ] Verify notifications

### Supply Chain Module
- [ ] View approved demands
- [ ] Generate test PO
- [ ] Enter supplier information
- [ ] Verify PO created

### QC Module
- [ ] View components pending QC
- [ ] Approve with good quantity
- [ ] View products pending QC
- [ ] Approve product
- [ ] Verify items sent to store

### Store Module
- [ ] View QC approved items
- [ ] Enter items to categories
- [ ] View inventory by category
- [ ] Create issue
- [ ] View issue history

## Network Access Testing

- [ ] Find server IP address (`ipconfig`)
- [ ] Access from another device on same WiFi
- [ ] Test on mobile device
- [ ] Test on tablet
- [ ] Verify responsive design

## Security Verification

- [ ] Test login with wrong credentials (should fail)
- [ ] Test accessing module without permission (should redirect)
- [ ] Verify passwords are hashed in database
- [ ] Test SQL injection prevention (try entering `' OR '1'='1` in forms)
- [ ] Verify session timeout works

## Performance Testing

- [ ] Create 10+ BOMs
- [ ] Create 20+ demand notes
- [ ] Generate multiple POs
- [ ] Check page load times
- [ ] Test with multiple users simultaneously

## Production Deployment

- [ ] Change `SECRET_KEY` in `.env` to strong random value
- [ ] Set `FLASK_ENV=production`
- [ ] Consider using Waitress for production:
  ```powershell
  pip install waitress
  waitress-serve --host=0.0.0.0 --port=5000 app:app
  ```
- [ ] Set up automatic backup for MySQL database
- [ ] Document backup/restore procedures
- [ ] Create admin user guide
- [ ] Train users on system

## Optional Enhancements

- [ ] Add company logo (`static/images/logo.png`)
- [ ] Create print layout for POs
- [ ] Create print layout for demand notes
- [ ] Implement notification panel UI
- [ ] Add search functionality
- [ ] Add Excel export features
- [ ] Set up email notifications
- [ ] Create audit log system

## Maintenance

- [ ] Schedule regular database backups
- [ ] Monitor disk space
- [ ] Check MySQL logs periodically
- [ ] Update Python packages as needed
- [ ] Review user access periodically
- [ ] Archive old data as needed

---

**Notes:**
- Check off items as you complete them
- Keep this checklist for reference during deployment
- Update based on your specific requirements
