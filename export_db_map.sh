PUBLIC_HTML=/var/www/html
MDDB_DIR=$HOME/scripts
DATE=$(date +%Y-%m-%d)
LOGFILE=$MDDB_DIR/logs/$DATE.log
. $MDDB_DIR/dolibarr_db_pass.sh

mkdir -p $PUBLIC_HTML/$DATE
#generation des donnees pour la mise a jour des cartes
cd $PUBLIC_HTML/$DATE
python3 $MDDB_DIR/manage_dolibarr_db.py export -f json >> $LOGFILE 2>&1
python3 $MDDB_DIR/manage_dolibarr_db.py export -f csv >> $LOGFILE 2>&1
python3 $MDDB_DIR/manage_dolibarr_db.py update --dry_run >> $LOGFILE 2>&1
cd ..
rm current
ln -s $DATE current
