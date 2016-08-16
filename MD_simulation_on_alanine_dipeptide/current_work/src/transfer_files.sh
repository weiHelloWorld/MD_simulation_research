#!/bin/bash

# this script sync between server and local machine

PROJECT_DIR=$1
FOLDER_TO_SEND=$2

FOLDER_IN_CLUSTER="weichen9/current_work"

if [[ ${PROJECT_DIR} = "" ]] || [[ ${FOLDER_TO_SEND} = "" ]]; then
	echo "missing parameters!"
else
	echo "sync files between local machine and ALF server"
	echo "-----------------------------------------------"

	echo "-----------------------------------------------"
	echo "sending ${FOLDER_TO_SEND}"
	echo "-----------------------------------------------"
	echo ""
	rsync -urv ${PROJECT_DIR}/${FOLDER_TO_SEND} weichen9@alf-clustersrv.mrl.illinois.edu:~/${FOLDER_IN_CLUSTER}    # transfer src folder to ALF

	echo "-----------------------------------------------"
	echo "receiving resources"
	echo "-----------------------------------------------"
	echo ""
	rsync -urv weichen9@alf-clustersrv.mrl.illinois.edu:~/${FOLDER_IN_CLUSTER}/resources ${PROJECT_DIR}/    # get back resources ALF

	echo "-----------------------------------------------"
	echo "receiving target"
	echo "-----------------------------------------------"
	echo ""
	rsync -urv weichen9@alf-clustersrv.mrl.illinois.edu:~/${FOLDER_IN_CLUSTER}/target ${PROJECT_DIR}/    # get back target ALF
fi
