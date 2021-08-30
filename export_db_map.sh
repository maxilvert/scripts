PUBLIC_HTML=/var/www/html
MDDB_DIR=$HOME/scripts
DATE=$(date +%Y-%m-%d)

mkdir -p $PUBLIC_HTML/$DATE
cd $PUBLIC_HTML/$DATE
python3 $MDDB_DIR/manage_dolibarr_db.py export -f json > $MDDB_DIR/logs/$DATE.log 2>&1
python3 $MDDB_DIR/manage_dolibarr_db.py export -f csv 
cd ..
ls
rm current
ln -s $DATE current
