PUBLIC_HTML=/var/www/html
MDDB_DIR=$HOME/scripts
DATE=$(date +%Y-%m-%d)
source $MDDB_DIR/dolibarr_db_pass.sh

mkdir -p $PUBLIC_HTML/$DATE
cd $PUBLIC_HTML/$DATE
python3 $MDDB_DIR/manage_dolibarr_db.py export -f json > $MDDB_DIR/logs/$DATE.log 2>&1
python3 $MDDB_DIR/manage_dolibarr_db.py export -f csv 
python3 $MDDB_DIR/manage_dolibarr_db.py update --dry_run >> $MDDB_DIR/logs/$DATE.log 2>&1
cd ..
ls
rm current
ln -s $DATE current
